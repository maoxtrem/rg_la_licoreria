"""Regresión de pendientes, cobro y cierre de facturas contra la API local."""
import secrets
import json
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
        status_code, result = self.sales('/checkout', 'POST', {'status': status, 'checkout_key': key, **({'cash_received': self.sales()[1]['data']['total']} if status == 'paid' else {})})
        self.assertEqual(status_code, 201, result)
        self.assertEqual(result['cart']['items'], [])
        if status == 'paid':
            self.assertEqual(result['printing']['status'], 'queued')
        else:
            self.assertNotIn('printing', result)
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
        status, paid = self.billing(path + '/pay', 'POST', {'revision': revision, 'cash_received': '30.00'})
        self.assertEqual(status, 200, paid)
        self.assertEqual(paid['data']['status'], 'paid')
        self.assertEqual(paid['printing']['status'], 'queued')
        self.assertIsNotNone(paid['data']['paid_at'])
        self.assertIsNotNone(paid['data']['company'])
        self.assertEqual(paid['data']['cash_received'], '30.00')
        self.assertEqual(paid['data']['payment_method'], 'cash')
        self.assertEqual(paid['data']['change_due'], '5.00')
        self.assertEqual(self.billing(path, 'PATCH', {'revision': paid['data']['revision'], 'items': change['items']})[0], 409)
        self.assertEqual(self.billing(path + '/pay', 'POST', {'revision': paid['data']['revision'], 'cash_received': '30.00'})[0], 409)
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

    def test_billing_number_filter_and_readonly_detail(self):
        group = self.prepare_billing()
        product = self.sell_product()
        invoice, _ = self.checkout(product)
        other, _ = self.checkout(product, 'paid')
        self.grant(group, ['billing.view'])
        for number in [invoice['number'], str(invoice['id']), invoice['number'].lower()]:
            status, result = self.billing('?number=' + number + '&limit=1')
            self.assertEqual(status, 200, result)
            self.assertEqual([entry['id'] for entry in result['data']], [invoice['id']])
            self.assertEqual(result['pagination']['total'], 1)
        for suffix in ['&status=paid', '&page=2&limit=1']:
            status, result = self.billing('?number=' + invoice['number'] + suffix)
            self.assertEqual(status, 200)
            self.assertEqual(result['data'], [])
        self.assertEqual(self.billing('?number=0')[1]['pagination']['total'], 0)
        for number in ['invalid', 'F-', '-1', '1%25', '9' * 21]:
            self.assertEqual(self.billing('?number=' + number)[0], 422)
        self.assertEqual(self.billing(f'/{invoice["id"]}')[1]['data'], invoice)
        self.assertEqual(self.billing(f'/{other["id"]}')[1]['data'], other)

    def test_billing_date_range_colombia_boundaries(self):
        self.prepare_billing()
        product = self.sell_product()
        invoices = [self.checkout(product)[0] for _ in range(4)]
        today_invoice, _ = self.checkout(product)
        timestamps = ['2024-01-02 04:59:59', '2024-01-02 05:00:00', '2024-01-03 04:59:59', '2024-01-03 05:00:00']
        code = r'''<?php
require 'vendor/autoload.php';
(new Symfony\Component\Dotenv\Dotenv())->bootEnv('.env');
$kernel = new App\Kernel($_ENV['APP_ENV'], true); $kernel->boot();
$connection = $kernel->getContainer()->get('doctrine')->getConnection();
foreach (json_decode(getenv('SMOKE_INVOICE_DATES'), true) as $id => $date) {
    $connection->update('invoice', ['created_at' => $date], ['id' => $id]);
}
'''
        dates = json.dumps({invoice['id']: date for invoice, date in zip(invoices, timestamps)})
        subprocess.run(['docker', 'compose', '--env-file', 'app/.env.local', 'exec', '-T', '-e', 'SMOKE_INVOICE_DATES=' + dates, 'php', 'php'], cwd=api_auth_smoke.ROOT, input=code, text=True, check=True, capture_output=True)
        status, result = self.billing('?from=2024-01-02&to=2024-01-02&limit=1')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['pagination']['total'], 2)
        self.assertEqual([i['id'] for i in result['data']], [invoices[2]['id']])
        result = self.billing('?from=2024-01-02&to=2024-01-02&limit=1&page=2')[1]
        self.assertEqual([i['id'] for i in result['data']], [invoices[1]['id']])
        self.assertEqual(self.billing('?from=2024-01-02&to=2024-01-02&number=' + invoices[0]['number'])[1]['data'], [])
        self.assertEqual(self.billing('?from=2024-01-02&to=2024-01-02&status=paid')[1]['pagination']['total'], 0)
        self.assertIn(today_invoice['id'], [i['id'] for i in self.billing()[1]['data']])
        self.assertEqual(self.billing('?number=' + invoices[1]['number'])[1]['data'], [])
        self.assertEqual(self.billing('?from=&to=&number=' + invoices[1]['number'])[1]['pagination']['total'], 1)
        for query in ['from=2024-02-30', 'to=invalid', 'from=2024-1-2', 'from=2024-01-03&to=2024-01-02']:
            self.assertEqual(self.billing('?' + query)[0], 422)

    def test_billing_snapshot_survives_catalog_changes_and_deletion(self):
        self.prepare_billing()
        product = self.sell_product('12.35')
        pending, _ = self.checkout(product)
        paid, _ = self.checkout(product, 'paid')
        with self.admin_session():
            status, result = self.product_request(f'/api/products/{product["id"]}', 'PATCH', {
                'name': 'Producto renombrado', 'barcode': 'changed-' + secrets.token_hex(8), 'sale_price': '99.99',
            }, self.tokens()['products'])
            self.assertEqual(status, 200, result)
        for invoice in [pending, paid]:
            self.assertNotIn('image_url', invoice['items'][0])
            self.assertEqual(self.billing(f'/{invoice["id"]}')[1]['data'], invoice)
        with self.admin_session():
            self.assertEqual(self.product_request(f'/api/products/{product["id"]}', 'DELETE', csrf=self.tokens()['products'])[0], 204)
        for invoice in [pending, paid]:
            self.assertEqual(self.billing(f'/{invoice["id"]}')[1]['data'], invoice)
        status, edited = self.billing(f'/{pending["id"]}', 'PATCH', {
            'revision': pending['revision'], 'items': [{'product_id': product['id'], 'quantity': 2}],
        })
        self.assertEqual(status, 200, edited)
        self.assertEqual(edited['data']['items'][0]['name'], product['name'])
        self.assertEqual(edited['data']['items'][0]['barcode'], product['barcode'])
        self.assertEqual(edited['data']['items'][0]['unit_price'], '12.35')
        self.assertEqual(edited['data']['total'], '24.70')
        status, finalized = self.billing(f'/{pending["id"]}/pay', 'POST', {'revision': edited['data']['revision'], 'cash_received': '25.00'})
        self.assertEqual(status, 200, finalized)
        self.assertEqual(finalized['data']['items'], edited['data']['items'])

    def test_billing_cash_validation_and_checkout_persistence(self):
        self.prepare_billing()
        product = self.sell_product('12.35')
        self.assertEqual(self.scan(product)[0], 200)
        key = self.sales()[1]['data']['checkout_key']
        for value in [None, 20, '12.34', '-1.00', '20.001', '1e3', '9' * 16 + '.00']:
            status, result = self.sales('/checkout', 'POST', {'status': 'paid', 'checkout_key': key, 'cash_received': value})
            self.assertEqual(status, 422, result)
            self.assertEqual(self.sales()[1]['data']['checkout_key'], key)
        payload = {'status': 'paid', 'checkout_key': key, 'cash_received': '20.00'}
        status, result = self.sales('/checkout', 'POST', payload)
        self.assertEqual(status, 201, result)
        invoice = result['data']
        self.assertEqual(invoice['cash_received'], '20.00')
        self.assertEqual(invoice['change_due'], '7.65')
        payload['cash_received'] = '99.00'
        repeated = self.sales('/checkout', 'POST', payload)[1]
        self.assertEqual(repeated['data'], invoice)
        self.assertEqual(repeated['printing']['print_job_id'], result['printing']['print_job_id'])
        self.assertEqual(self.billing(f'/{invoice["id"]}')[1]['data'], invoice)
        pending, _ = self.checkout(product)
        path = f'/{pending["id"]}'
        self.assertIsNone(pending['cash_received'])
        self.assertIsNone(pending['change_due'])
        for value in [None, '12.34', 'bad', 20]:
            self.assertEqual(self.billing(path + '/pay', 'POST', {'revision': pending['revision'], 'cash_received': value})[0], 422)
            self.assertEqual(self.billing(path)[1]['data'], pending)
        status, paid = self.billing(path + '/pay', 'POST', {'revision': pending['revision'], 'cash_received': '12.35'})
        self.assertEqual(status, 200, paid)
        self.assertEqual(paid['data']['change_due'], '0.00')

    def test_billing_transfer_from_sales_and_pending_invoice(self):
        self.prepare_billing()
        product = self.sell_product('12.35')
        self.assertEqual(self.scan(product)[0], 200)
        key = self.sales()[1]['data']['checkout_key']
        for extra in [{'payment_method': 'card'}, {'payment_method': None}, {'payment_method': 'transfer', 'cash_received': '20.00'}]:
            self.assertEqual(self.sales('/checkout', 'POST', {'status': 'paid', 'checkout_key': key, **extra})[0], 422)
        payload = {'status': 'paid', 'checkout_key': key, 'payment_method': 'transfer'}
        status, result = self.sales('/checkout', 'POST', payload)
        self.assertEqual(status, 201, result)
        direct = result['data']
        self.assertEqual(direct['payment_method'], 'transfer')
        self.assertIsNone(direct['cash_received'])
        self.assertIsNone(direct['change_due'])
        self.assertEqual(result['printing']['status'], 'queued')
        repeated = self.sales('/checkout', 'POST', payload)[1]
        self.assertEqual(repeated['data'], direct)
        self.assertEqual(repeated['printing'], result['printing'])
        self.assertEqual(self.billing(f'/{direct["id"]}')[1]['data'], direct)
        pending, _ = self.checkout(product)
        self.assertIsNone(pending['payment_method'])
        path = f'/{pending["id"]}'
        for extra in [{'payment_method': 'other'}, {'payment_method': 'transfer', 'cash_received': '99.00'}]:
            self.assertEqual(self.billing(path + '/pay', 'POST', {'revision': pending['revision'], **extra})[0], 422)
            self.assertEqual(self.billing(path)[1]['data'], pending)
        status, paid = self.billing(path + '/pay', 'POST', {'revision': pending['revision'], 'payment_method': 'transfer'})
        self.assertEqual(status, 200, paid)
        self.assertEqual(paid['data']['payment_method'], 'transfer')
        self.assertIsNone(paid['data']['cash_received'])
        self.assertIsNone(paid['data']['change_due'])
        self.assertEqual(paid['printing']['status'], 'queued')
        self.assertEqual(self.billing(path)[1]['data'], paid['data'])
        self.assertEqual(self.billing(path + '/pay', 'POST', {'revision': paid['data']['revision'], 'payment_method': 'cash', 'cash_received': '20.00'})[0], 409)

    def test_billing_split_payment_and_change(self):
        self.prepare_billing()
        product = self.sell_product('100.50')
        self.assertEqual(self.scan(product)[0], 200)
        key = self.sales()[1]['data']['checkout_key']
        for cash, transfer in [('50.00', '50.00'), ('0.00', '101.00'), ('100.50', '-1.00'), ('100.50', None), ('bad', '0.00')]:
            self.assertEqual(self.sales('/checkout', 'POST', {'status': 'paid', 'checkout_key': key, 'cash_received': cash, 'transfer_received': transfer})[0], 422)
            self.assertEqual(self.sales()[1]['data']['checkout_key'], key)
        status, result = self.sales('/checkout', 'POST', {'status': 'paid', 'checkout_key': key, 'cash_received': '80.00', 'transfer_received': '30.50'})
        self.assertEqual(status, 201, result)
        invoice = result['data']
        self.assertEqual((invoice['payment_method'], invoice['cash_received'], invoice['transfer_received'], invoice['change_due']), ('mixed', '80.00', '30.50', '10.00'))
        self.assertEqual(result['printing']['status'], 'queued')
        self.assertEqual(self.billing(f'/{invoice["id"]}')[1]['data'], invoice)
        pending, _ = self.checkout(product)
        path = f'/{pending["id"]}'
        status, paid = self.billing(path + '/pay', 'POST', {'revision': pending['revision'], 'cash_received': '0.00', 'transfer_received': '100.50'})
        self.assertEqual(status, 200, paid)
        self.assertEqual(paid['data']['payment_method'], 'transfer')
        self.assertEqual(paid['data']['cash_received'], '0.00')
        self.assertEqual(paid['data']['change_due'], '0.00')
        self.assertEqual(paid['data']['transfer_received'], '100.50')
        self.assertEqual(paid['printing']['status'], 'queued')
        self.assertEqual(self.billing(path)[1]['data'], paid['data'])

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
