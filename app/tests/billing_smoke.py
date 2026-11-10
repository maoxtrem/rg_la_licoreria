"""Regresión de pendientes, cobro y cierre de facturas contra la API local."""
import secrets
import subprocess
import unittest

import api_auth_smoke
from sales_smoke import SalesApiTest
from company_smoke import CompanyApiTest


class BillingApiTest(SalesApiTest):
    def prepare_billing(self):
        group = self.prepare_sales()
        self.grant(group, ['sales.' + action for action in ['view', 'create', 'update', 'delete']] + ['billing.view', 'billing.update'])
        status, result = self.admin_api('/api/company')
        self.assertEqual(status, 200)
        if result['data'] is None:
            name = 'billing_smoke_' + secrets.token_hex(8)
            self.addCleanup(CompanyApiTest.remove_test_company, self, name)
            self.assertEqual(self.admin_api('/api/company', 'POST', {'name': name, 'address': 'Calle de prueba', 'phone': '1234567', 'nit': '000-0'}, 'company')[0], 201)
        self.addCleanup(self.remove_invoices)
        return group

    def remove_invoices(self):
        code = r'''<?php
require 'vendor/autoload.php';
(new Symfony\Component\Dotenv\Dotenv())->bootEnv('.env');
$kernel = new App\Kernel($_ENV['APP_ENV'], true); $kernel->boot();
$em = $kernel->getContainer()->get('doctrine')->getManager();
$em->createQuery('DELETE FROM App\Entity\Invoice i WHERE i.createdBy = :id')->setParameter('id', (int) getenv('SMOKE_USER_ID'))->execute();
'''
        subprocess.run(['docker', 'compose', '--env-file', 'app/.env.local', 'exec', '-T', '-e', f'SMOKE_USER_ID={self.user_id}', 'php', 'php'], cwd=api_auth_smoke.ROOT, input=code, text=True, check=True, capture_output=True)

    def billing(self, suffix='', method='GET', data=None, csrf=True):
        return self.product_request('/api/billing' + suffix, method, data, self.tokens()['billing'] if csrf and method != 'GET' else None)

    def checkout(self, product, status='pending'):
        self.assertEqual(self.scan(product)[0], 200)
        key = self.sales()[1]['data']['checkout_key']
        status_code, result = self.sales('/checkout', 'POST', {'status': status, 'checkout_key': key})
        self.assertEqual(status_code, 201, result)
        self.assertEqual(result['cart']['items'], [])
        return result['data'], key

    def test_billing_pending_edit_pay_and_paid_lock(self):
        self.prepare_billing()
        first, second = self.sell_product('12.35'), self.sell_product('0.10')
        invoice, key = self.checkout(first)
        path = f'/{invoice["id"]}'
        # Repeated checkout cannot create a second invoice.
        duplicate = self.sales('/checkout', 'POST', {'status': 'pending', 'checkout_key': key})[1]['data']
        self.assertEqual(duplicate['id'], invoice['id'])
        self.assertEqual(self.billing(path + '/print', 'POST', {'print_job_id': secrets.token_hex(16)})[0], 409)
        status, lookup = self.billing('/product?barcode=' + second['barcode'])
        self.assertEqual(status, 200)
        self.assertNotIn('cost_price', lookup['data'])
        change = {'revision': invoice['revision'], 'items': [{'product_id': first['id'], 'quantity': 2}, {'product_id': second['id'], 'quantity': 3}]}
        self.assertEqual(self.billing(path, 'PATCH', change, csrf=False)[0], 403)
        status, edited = self.billing(path, 'PATCH', change)
        self.assertEqual(status, 200, edited)
        self.assertEqual(edited['data']['total'], '25.00')
        self.assertEqual(self.billing(path, 'PATCH', change)[0], 409)
        revision = edited['data']['revision']
        status, paid = self.billing(path + '/pay', 'POST', {'revision': revision})
        self.assertEqual(status, 200, paid)
        self.assertEqual(paid['data']['status'], 'paid')
        self.assertIsNotNone(paid['data']['paid_at'])
        self.assertIsNotNone(paid['data']['company'])
        self.assertEqual(self.billing(path, 'PATCH', {'revision': paid['data']['revision'], 'items': change['items']})[0], 409)
        self.assertEqual(self.billing(path + '/pay', 'POST', {'revision': paid['data']['revision']})[0], 409)
        self.assertEqual(self.billing(path)[1]['data'], paid['data'])

    def test_billing_multiple_pending_and_direct_paid(self):
        self.prepare_billing()
        product = self.sell_product()
        first, _ = self.checkout(product)
        second, _ = self.checkout(product)
        paid, _ = self.checkout(product, 'paid')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(paid['status'], 'paid')
        pending_ids = [entry['id'] for entry in self.billing('?status=pending')[1]['data']]
        self.assertIn(first['id'], pending_ids)
        self.assertIn(second['id'], pending_ids)
        self.assertNotIn(paid['id'], pending_ids)
        self.assertEqual(self.billing(f'/{paid["id"]}', 'PATCH', {'revision': paid['revision'], 'items': []})[0], 409)

    def test_billing_permissions_and_invalid_edit(self):
        group = self.prepare_billing()
        product = self.sell_product()
        invoice, _ = self.checkout(product)
        path = f'/{invoice["id"]}'
        for items in [[], [{'product_id': product['id'], 'quantity': 0}], [{'product_id': product['id'], 'quantity': 1}] * 2]:
            self.assertEqual(self.billing(path, 'PATCH', {'revision': invoice['revision'], 'items': items})[0], 422)
        self.grant(group, ['billing.view'])
        self.assertEqual(self.billing()[0], 200)
        self.assertEqual(self.billing(path, 'PATCH', {'revision': invoice['revision'], 'items': []})[0], 403)
        self.assertEqual(self.billing(path + '/pay', 'POST', {'revision': invoice['revision']})[0], 403)
        self.assertEqual(self.billing('/product?barcode=' + product['barcode'])[0], 403)
        self.grant(group, [])
        self.assertEqual(self.billing()[0], 403)


if __name__ == '__main__':
    names = ['BillingApiTest.' + name for name in BillingApiTest.__dict__ if name.startswith('test_billing_')]
    unittest.main(defaultTest=names, verbosity=2)
