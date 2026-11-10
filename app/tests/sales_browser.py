"""Ventas con lector y regresión de productos/alertas en Chromium."""
import os
import secrets
import unittest

from playwright.sync_api import expect
import products_browser


class SalesBrowserTest(products_browser.ProductsBrowserTest):
    def login_sales(self, normal=False, actions=None):
        if actions is not None:
            self.grant(['sales.' + action for action in actions])
        self.page.goto(products_browser.BASE + '/login')
        self.page.locator('#username').fill(os.environ['SMOKE_USERNAME'] if normal else 'admin')
        self.page.locator('#password').fill(os.environ['SMOKE_PASSWORD'] if normal else 'admin')
        self.page.locator('#login-button').click()
        self.page.wait_for_url(products_browser.BASE + '/')
        self.page.goto(products_browser.BASE + '/ventas')
        expect(self.page.locator('#sales-view')).to_be_visible()
        expect(self.page.locator('#sales-scan-status')).to_contain_text('0 unidades')

    def scan(self, barcode):
        self.page.locator('#sales-barcode').fill(barcode)
        with self.page.expect_response(lambda response: '/api/sales/cart/items' in response.url and response.request.method == 'POST') as result:
            self.page.locator('#sales-barcode').press('Enter')
        self.assertEqual(result.value.status, 200)

    def refresh_sales(self):
        with self.page.expect_response(lambda response: response.url.endswith('/api/sales/cart') and response.request.method == 'GET'):
            self.page.locator('#sales-refresh').click()
        expect(self.page.locator('#sales-refresh')).to_be_enabled()

    def test_sales_scanner_focus_repetition_and_different_product(self):
        first, second = self.create_api(), self.create_api()
        self.login_sales()
        expect(self.page.locator('#sales-barcode')).to_be_focused()
        for code in [first['barcode'], first['barcode'], second['barcode']]:
            self.scan(code)
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('3')
        expect(self.page.locator('#sales-summary-lines')).to_have_text('2')
        expect(self.page.locator('#sales-total')).to_have_text('135.001,50')
        expect(self.page.locator(f'tr[data-product-id="{first["id"]}"] input')).to_have_value('2')
        expect(self.page.locator('#sales-barcode')).to_be_focused()
        self.page.reload()
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('3')
        expect(self.page.locator('#sales-barcode')).to_be_focused()

    def test_sales_fast_scans_are_queued_without_loss(self):
        first, second = self.create_api(), self.create_api()
        self.login_sales()
        self.page.evaluate('''(codes) => {
            const input = document.getElementById('sales-barcode');
            const form = document.getElementById('sales-scan-form');
            for (const code of codes) { input.value = code; form.requestSubmit(); }
        }''', [first['barcode'], first['barcode'], second['barcode'], first['barcode']])
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('4')
        expect(self.page.locator('#sales-summary-lines')).to_have_text('2')
        expect(self.page.locator(f'tr[data-product-id="{first["id"]}"] input')).to_have_value('3')
        expect(self.page.locator('#sales-barcode')).to_be_focused()

    def test_sales_permissions_apply_to_each_action(self):
        product = self.create_api()
        self.login_sales(normal=True, actions=['view'])
        expect(self.page.locator('#sales-barcode')).to_be_disabled()
        self.grant(['sales.view', 'sales.create'])
        self.refresh_sales()
        expect(self.page.locator('#sales-barcode')).to_be_enabled()
        self.scan(product['barcode'])
        self.scan(product['barcode'])
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('2')
        expect(self.page.locator('#sales-rows input')).to_have_count(0)
        expect(self.page.locator('#sales-rows button')).to_have_count(0)
        expect(self.page.locator('#sales-clear')).to_be_hidden()
        self.grant(['sales.view', 'sales.update'])
        self.refresh_sales()
        expect(self.page.locator('#sales-barcode')).to_be_disabled()
        self.page.get_by_role('button', name='Sumar unidad de ' + product['name'], exact=True).click()
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('3')
        self.grant(['sales.view', 'sales.delete'])
        self.refresh_sales()
        expect(self.page.locator('#sales-rows input')).to_have_count(0)
        self.page.get_by_role('button', name='Retirar ' + product['name'], exact=True).click()
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('0')

    def test_sales_unknown_barcode_alert_and_focus_recovery(self):
        self.login_sales()
        self.page.locator('#sales-barcode').fill('unknown_' + secrets.token_hex(8))
        self.page.locator('#sales-barcode').press('Enter')
        expect(self.page.locator('.swal2-popup')).to_contain_text('No encontramos un producto')
        self.page.locator('.swal2-confirm').click()
        expect(self.page.locator('#sales-barcode')).to_be_focused()
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('0')

    def test_sales_revoked_create_permission_stops_scans(self):
        product = self.create_api()
        self.login_sales(normal=True, actions=['view', 'create'])
        self.scan(product['barcode'])
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('1')
        self.grant(['sales.view'])
        writes = []
        self.page.on('request', lambda request: writes.append(request.url) if '/api/sales/cart/items' in request.url and request.method == 'POST' else None)
        self.page.locator('#sales-barcode').fill(product['barcode'])
        self.page.locator('#sales-barcode').press('Enter')
        expect(self.page.locator('.swal2-popup')).to_contain_text('Tu grupo no tiene permiso')
        expect(self.page.locator('.swal2-image')).to_be_visible()
        expect(self.page.locator('#sales-barcode')).to_be_disabled()
        self.assertEqual(writes, [])
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('1')

    def test_sales_clear_requires_confirmation(self):
        product = self.create_api()
        self.login_sales()
        self.scan(product['barcode'])
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('1')
        expect(self.page.locator('#sales-clear')).to_be_enabled()
        self.page.locator('#sales-clear').click()
        self.page.locator('.swal2-cancel').click()
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('1')
        self.page.locator('#sales-clear').click()
        self.page.locator('.swal2-confirm').click()
        expect(self.page.locator('#sales-empty')).to_be_visible()
        expect(self.page.locator('#sales-total')).to_have_text('0,00')
        expect(self.page.locator('#sales-barcode')).to_be_focused()

    def test_sales_mobile_and_no_view_access(self):
        product = self.create_api()
        self.login_sales(normal=True, actions=['view', 'create'])
        self.scan(product['barcode'])
        expect(self.page.locator('#sales-summary-quantity')).to_have_text('1')
        self.page.screenshot(path='/tmp/sales-desktop.png', full_page=True)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.page.screenshot(path='/tmp/sales-mobile.png', full_page=True)
        self.grant([])
        self.page.locator('#sales-refresh').click()
        expect(self.page.locator('#access-denied-view img')).to_be_visible()
        expect(self.page.locator('#sales-view')).to_be_hidden()
        expect(self.page.locator('[data-nav][href="/ventas"]')).to_be_hidden()


if __name__ == '__main__':
    unittest.main(verbosity=2)
