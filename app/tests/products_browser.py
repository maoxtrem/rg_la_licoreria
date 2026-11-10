"""Pruebas reales de interfaz. Requiere Playwright y un usuario temporal ROLE_USER.

SMOKE_USERNAME y SMOKE_PASSWORD deben señalar el usuario temporal creado por
api_auth_smoke.ApiAuthenticationTest.fixture. Su grupo también debe ser temporal.
"""
import json
import os
import re
import secrets
import unittest

from playwright.sync_api import expect, sync_playwright

BASE = 'http://localhost'


class ProductsBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(args=['--no-sandbox'])
        cls.addClassCleanup(cls.browser.close)
        cls.admin = cls.playwright.request.new_context(base_url=BASE)
        cls.addClassCleanup(cls.admin.dispose)
        cls.api_login(cls.admin, 'admin', 'admin')
        user_api = cls.playwright.request.new_context(base_url=BASE)
        try:
            user = cls.api_login(user_api, os.environ['SMOKE_USERNAME'], os.environ['SMOKE_PASSWORD'])['user']
            cls.group_id = user['group']['id']
        finally:
            user_api.dispose()

    @staticmethod
    def api_login(client, username, password):
        csrf = client.get('/api/csrf').json()
        response = client.post('/api/login', data=json.dumps({'username': username, 'password': password, '_csrf_token': csrf['login']}), headers={'Content-Type': 'application/json'})
        assert response.status == 200, response.text()
        return response.json()

    def setUp(self):
        self.created = []
        self.context = self.browser.new_context(base_url=BASE, viewport={'width': 1440, 'height': 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.addCleanup(self.cleanup_data)
        self.grant(['products.view'])

    def cleanup_data(self):
        for product_id in self.created:
            response = self.mutate(f'/api/products/{product_id}', 'DELETE', token='products')
            self.assertIn(response.status, (204, 404))
        self.grant(['products.view'])
        self.assertEqual(self.errors, [])

    def mutate(self, path, method, payload=None, token='products'):
        csrf = self.admin.get('/api/csrf').json()[token]
        return self.admin.fetch(path, method=method, data=json.dumps(payload) if payload is not None else None,
                                headers={'Content-Type': 'application/json', 'X-CSRF-Token': csrf})

    def grant(self, keys):
        response = self.mutate(f'/api/groups/{self.group_id}/permissions', 'PUT', {'permissions': keys}, token='permissions')
        self.assertEqual(response.status, 200, response.text())

    def create_api(self, name=None):
        data = {'name': name or 'Browser ' + secrets.token_hex(6), 'barcode': '000' + secrets.token_hex(10),
                'sale_price': '45000.50', 'cost_price': '30000.10'}
        response = self.mutate('/api/products', 'POST', data)
        self.assertEqual(response.status, 201, response.text())
        product = response.json()['data']
        self.created.append(product['id'])
        return product

    def login_ui(self, normal=False):
        self.page.goto(BASE + '/login')
        self.page.locator('#username').fill(os.environ['SMOKE_USERNAME'] if normal else 'admin')
        self.page.locator('#password').fill(os.environ['SMOKE_PASSWORD'] if normal else 'admin')
        self.page.locator('#login-button').click()
        self.page.wait_for_url(BASE + '/')
        self.page.goto(BASE + '/productos')
        expect(self.page.locator('#products-view')).to_be_visible()
        expect(self.page.locator('#products-loading')).to_be_hidden()

    def refresh(self):
        with self.page.expect_response(lambda response: '/api/products?' in response.url):
            self.page.locator('#products-refresh').click()
        expect(self.page.locator('#products-loading')).to_be_hidden()

    def fill_product(self, name, barcode):
        self.page.locator('#product-name').fill(name)
        self.page.locator('#product-barcode').fill(barcode)
        self.page.locator('#product-sale-price').fill('45000,50')
        self.page.locator('#product-cost-price').fill('30000.10')

    def save(self, method):
        with self.page.expect_response(lambda response: '/api/products' in response.url and response.request.method == method) as result:
            self.page.locator('#product-save').click()
        return result.value

    def test_full_crud_and_delete_confirmation(self):
        self.login_ui()
        name = 'Ron <edición> & ' + secrets.token_hex(4)
        barcode = '000' + secrets.token_hex(10)
        self.page.locator('#product-create').click()
        expect(self.page.locator('#product-name')).to_be_focused()
        self.fill_product(name, barcode)
        response = self.save('POST')
        self.assertEqual(response.status, 201)
        product = response.json()['data']
        self.created.append(product['id'])
        self.assertEqual(product['sale_price'], '45000.50')
        self.assertEqual(product['barcode'], barcode)
        expect(self.page.locator('#product-dialog')).not_to_be_visible()
        row = self.page.locator('#products-rows tr').filter(has_text=name)
        expect(row).to_be_visible()
        expect(row).to_contain_text('45.000,50')
        expect(row.locator('img')).to_have_count(0)
        row.get_by_role('button', name='Editar ' + name, exact=True).click()
        expect(self.page.locator('#product-dialog')).to_be_visible()
        self.page.locator('#product-name').fill(name + ' actualizado')
        self.page.locator('#product-sale-price').fill('47000.25')
        self.assertEqual(self.save('PUT').status, 200)
        expect(self.page.locator('#product-dialog')).not_to_be_visible()
        row = self.page.locator('#products-rows tr').filter(has_text=name + ' actualizado')
        expect(row).to_contain_text('47.000,25')
        row.get_by_role('button', name=re.compile('^Eliminar ')).click()
        expect(self.page.locator('.swal2-cancel')).to_be_focused()
        self.page.locator('.swal2-cancel').click()
        expect(row).to_be_visible()
        row.get_by_role('button', name=re.compile('^Eliminar ')).click()
        with self.page.expect_response(lambda response: response.request.method == 'DELETE') as deleted:
            self.page.locator('.swal2-confirm').click()
        self.assertEqual(deleted.value.status, 204)
        expect(self.page.locator('.swal2-popup:not(.swal2-toast)')).not_to_be_visible()
        expect(row).to_have_count(0)
        expect(self.page.locator('.swal2-popup')).to_contain_text('eliminado correctamente')

    def test_duplicate_barcode_stays_in_form(self):
        product = self.create_api()
        self.login_ui()
        self.page.locator('#product-create').click()
        self.fill_product('Otro producto', product['barcode'])
        self.assertEqual(self.save('POST').status, 409)
        expect(self.page.locator('#product-dialog')).to_be_visible()
        expect(self.page.locator('#product-barcode')).to_have_attribute('aria-invalid', 'true')
        expect(self.page.locator('.swal2-popup')).to_be_visible()
        expect(self.page.locator('.swal2-popup')).to_contain_text('código de barras')
        self.page.locator('.swal2-confirm').click()
        expect(self.page.locator('#product-barcode-error')).to_contain_text('único')
        expect(self.page.locator('#product-barcode')).to_be_focused()

    def test_permissions_readonly_and_revocation_while_editing(self):
        product = self.create_api()
        self.login_ui(normal=True)
        expect(self.page.locator('#product-create')).to_be_hidden()
        expect(self.page.locator('#products-readonly')).to_be_visible()
        expect(self.page.locator('#products-rows button')).to_have_count(0)
        self.grant(['products.view', 'products.update'])
        self.refresh()
        expect(self.page.locator('#product-create')).to_be_hidden()
        expect(self.page.get_by_role('button', name='Eliminar ' + product['name'], exact=True)).to_have_count(0)
        self.page.get_by_role('button', name='Editar ' + product['name'], exact=True).click()
        self.page.locator('#product-name').fill('No debe guardarse')
        self.grant(['products.view'])
        writes = []
        self.page.on('request', lambda request: writes.append(request.method) if '/api/products/' in request.url and request.method == 'PUT' else None)
        self.page.locator('#product-save').click()
        expect(self.page.locator('#product-dialog')).not_to_be_visible()
        expect(self.page.locator('.swal2-popup')).to_contain_text('ya no tiene permiso')
        expect(self.page.locator('.swal2-image')).to_have_attribute('src', '/images/access-denied.svg')
        expect(self.page.locator('#products-rows button')).to_have_count(0)
        self.assertEqual(writes, [])
        self.assertEqual(self.admin.get(f'/api/products/{product["id"]}').json()['data']['name'], product['name'])

    def test_permissions_create_and_delete_are_independent(self):
        self.grant(['products.view', 'products.create'])
        self.login_ui(normal=True)
        expect(self.page.locator('#product-create')).to_be_visible()
        expect(self.page.locator('#products-rows button')).to_have_count(0)
        self.page.locator('#product-create').click()
        name = 'Usuario crea ' + secrets.token_hex(4)
        self.fill_product(name, '000' + secrets.token_hex(10))
        response = self.save('POST')
        self.assertEqual(response.status, 201)
        self.created.append(response.json()['data']['id'])
        expect(self.page.locator('#product-dialog')).not_to_be_visible()
        self.grant(['products.view', 'products.delete'])
        self.refresh()
        expect(self.page.locator('#product-create')).to_be_hidden()
        expect(self.page.get_by_role('button', name='Editar ' + name, exact=True)).to_have_count(0)
        self.page.get_by_role('button', name='Eliminar ' + name, exact=True).click()
        with self.page.expect_response(lambda response: response.request.method == 'DELETE') as result:
            self.page.locator('.swal2-confirm').click()
        self.assertEqual(result.value.status, 204)

    def test_no_view_permission_blocks_direct_navigation(self):
        self.grant([])
        self.api_login(self.context.request, os.environ['SMOKE_USERNAME'], os.environ['SMOKE_PASSWORD'])
        self.page.goto(BASE + '/productos')
        expect(self.page.locator('#access-denied-view')).to_be_visible()
        expect(self.page.locator('#access-denied-view img')).to_have_attribute('src', '/images/access-denied.svg')
        expect(self.page.locator('#products-view')).to_be_hidden()
        expect(self.page.locator('[data-nav][href="/productos"]')).to_be_hidden()

    def test_view_revoked_removes_module_and_data(self):
        self.create_api()
        self.login_ui(normal=True)
        self.grant([])
        self.page.locator('#products-refresh').click()
        expect(self.page.locator('#access-denied-view')).to_be_visible()
        expect(self.page.locator('#access-denied-view img')).to_have_attribute('src', '/images/access-denied.svg')
        expect(self.page.locator('#products-view')).to_be_hidden()
        expect(self.page.locator('[data-nav][href="/productos"]')).to_be_hidden()
        expect(self.page.locator('#products-rows tr')).to_have_count(0)

    def test_direct_forbidden_api_navigation_uses_custom_image(self):
        self.grant([])
        self.api_login(self.context.request, os.environ['SMOKE_USERNAME'], os.environ['SMOKE_PASSWORD'])
        for path in ['/api/products', '/api/admin']:
            response = self.page.goto(BASE + path)
            self.assertEqual(response.status, 403)
            expect(self.page.locator('.access-denied-image')).to_be_visible()
            expect(self.page.locator('h1')).to_have_text('Este espacio necesita permiso.')
            self.assertNotIn('Symfony Exception', self.page.content())
            self.assertEqual(self.page.locator('script[src="/scripts/app.js"]').count(), 0)
        response = self.context.request.get(BASE + '/api/products', headers={'Accept': 'application/json'})
        self.assertEqual(response.status, 403)
        self.assertIn('error', response.json())

    def test_login_error_uses_sweetalert(self):
        self.page.goto(BASE + '/login')
        self.page.locator('#username').fill('admin')
        self.page.locator('#password').fill('incorrect-password')
        self.page.locator('#login-button').click()
        expect(self.page.locator('.swal2-popup')).to_be_visible()
        expect(self.page.locator('.swal2-popup')).to_contain_text('No se pudo iniciar sesión')
        self.page.locator('.swal2-confirm').click()
        expect(self.page.locator('#password')).to_be_focused()

    def test_pagination(self):
        products = [self.create_api() for _ in range(21)]
        self.login_ui()
        expect(self.page.locator('#products-rows tr')).to_have_count(20)
        expect(self.page.locator('#products-next')).to_be_enabled()
        self.page.locator('#products-next').click()
        expect(self.page.locator('#products-page-number')).to_have_text(re.compile('2 de'))
        expect(self.page.locator('#products-rows')).to_contain_text(products[0]['barcode'])
        self.page.locator('#products-previous').click()
        expect(self.page.locator('#products-page-number')).to_have_text(re.compile('1 de'))
        expect(self.page.locator('#products-rows')).to_contain_text(products[-1]['barcode'])

    def test_list_network_failure_can_be_retried(self):
        self.page.route('**/api/products?*', lambda route: route.fulfill(status=503, content_type='application/json', body='{"error":"Temporal"}'))
        self.login_ui()
        expect(self.page.locator('.swal2-popup')).to_contain_text('No pudimos cargar')
        self.page.locator('.swal2-confirm').click()
        self.page.unroute('**/api/products?*')
        self.refresh()
        expect(self.page.locator('.swal2-popup')).to_be_hidden()

    def test_expired_session_returns_to_login(self):
        self.login_ui()
        self.context.clear_cookies()
        self.page.locator('#products-refresh').click()
        self.page.wait_for_url(BASE + '/login')
        expect(self.page.locator('#login-view')).to_be_visible()

    def test_mobile_layout_and_screenshots(self):
        self.create_api('Producto de muestra para vista móvil')
        self.login_ui()
        self.page.screenshot(path='/tmp/products-desktop.png', full_page=True)
        self.page.set_viewport_size({'width': 390, 'height': 844})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.page.screenshot(path='/tmp/products-mobile.png', full_page=True)
        self.page.locator('#product-create').click()
        expect(self.page.locator('#product-dialog')).to_be_visible()
        self.assertTrue(self.page.locator('#product-dialog').evaluate('(dialog) => dialog.scrollWidth <= dialog.clientWidth'))
        self.page.screenshot(path='/tmp/products-mobile-form.png', full_page=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
