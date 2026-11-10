"""Ventas -> pendiente editable -> cobro -> factura de solo impresión."""
import os
import unittest

from playwright.sync_api import expect
import products_browser


class BillingBrowserTest(products_browser.ProductsBrowserTest):
    def setUp(self):
        super().setUp()
        self.grant(['sales.' + action for action in ['view', 'create', 'update', 'delete']] + ['billing.view', 'billing.update'])
        if self.admin.get('/api/company').json()['data'] is None:
            result = self.mutate('/api/company', 'POST', {'name': os.environ['SMOKE_USERNAME'], 'address': 'Calle prueba', 'phone': '0012345', 'nit': '00123-4'}, token='company')
            self.assertEqual(result.status, 201, result.text())
        self.page.goto(products_browser.BASE + '/login')
        self.page.locator('#username').fill(os.environ['SMOKE_USERNAME'])
        self.page.locator('#password').fill(os.environ['SMOKE_PASSWORD'])
        self.page.locator('#login-button').click()
        self.page.wait_for_url(products_browser.BASE + '/')
        self.page.get_by_role('link', name='Ventas', exact=True).click()
        expect(self.page.locator('#sales-scan-status')).to_contain_text('0 unidades')

    def scan_product(self):
        product = self.create_api(name='Producto factura prueba')
        self.page.locator('#sales-barcode').fill(product['barcode'])
        self.page.locator('#sales-barcode').press('Enter')
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('1')
        return product

    def test_pending_edit_pay_and_print_action(self):
        product = self.scan_product()
        with self.page.expect_response(lambda r: r.url.endswith('/api/sales/cart/checkout')) as result:
            self.page.locator('#sales-pending').click()
        self.assertEqual(result.value.status, 201)
        invoice = result.value.json()['data']
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('0')
        self.page.get_by_role('link', name='Facturación', exact=True).click()
        row = self.page.locator(f'tr[data-invoice-id="{invoice["id"]}"]')
        expect(row).to_contain_text('Pendiente de pago')
        row.get_by_role('button', name='Editar ' + invoice['number'], exact=True).click()
        expect(row.get_by_role('button', name='Imprimir ' + invoice['number'], exact=True)).to_have_count(0)
        quantity = self.page.get_by_role('spinbutton', name='Cantidad de ' + product['name'])
        quantity.fill('3')
        quantity.press('Tab')
        with self.page.expect_response(lambda r: '/api/billing/' in r.url and r.request.method == 'PATCH') as saved:
            self.page.locator('#billing-save').click()
        self.assertEqual(saved.value.status, 200)
        expect(self.page.locator('#billing-dialog')).to_be_hidden()
        row.get_by_role('button', name='Pagar ' + invoice['number'], exact=True).click()
        with self.page.expect_response(lambda r: r.url.endswith('/pay')) as paid:
            self.page.locator('.swal2-confirm').click()
        self.assertEqual(paid.value.status, 200)
        expect(row.get_by_role('button', name='Imprimir ' + invoice['number'], exact=True)).to_be_visible()
        expect(row.get_by_role('button', name='Editar ' + invoice['number'], exact=True)).to_have_count(0)
        expect(row.get_by_role('button', name='Pagar ' + invoice['number'], exact=True)).to_have_count(0)
        # UI queue acknowledgement without printing a physical test ticket.
        self.page.route('**/api/billing/*/print', lambda route: route.fulfill(status=202, content_type='application/json', body='{"status":"queued"}'))
        with self.page.expect_response(lambda r: r.url.endswith('/print')) as printed:
            row.get_by_role('button', name='Imprimir ' + invoice['number'], exact=True).click()
        self.assertEqual(printed.value.status, 202)
        self.page.reload()
        expect(self.page.locator(f'tr[data-invoice-id="{invoice["id"]}"]')).to_contain_text('Facturada')

    def test_direct_payment_from_sales(self):
        self.scan_product()
        self.page.locator('#sales-pay').click()
        with self.page.expect_response(lambda r: r.url.endswith('/api/sales/cart/checkout')) as result:
            self.page.locator('.swal2-confirm').click()
        self.assertEqual(result.value.status, 201)
        invoice = result.value.json()['data']
        self.assertEqual(invoice['status'], 'paid')
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('0')
        self.page.get_by_role('link', name='Facturación', exact=True).click()
        row = self.page.locator(f'tr[data-invoice-id="{invoice["id"]}"]')
        expect(row).to_contain_text('Facturada')
        expect(row.get_by_role('button', name='Imprimir ' + invoice['number'], exact=True)).to_be_visible()
        expect(row.get_by_role('button')).to_have_count(1)


if __name__ == '__main__':
    unittest.main(defaultTest=['BillingBrowserTest.test_pending_edit_pay_and_print_action', 'BillingBrowserTest.test_direct_payment_from_sales'], verbosity=2)
