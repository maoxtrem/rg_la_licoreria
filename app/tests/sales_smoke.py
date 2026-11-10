"""Carrito de ventas y regresión de permisos: python3 app/tests/sales_smoke.py."""
import secrets
import base64
import unittest

import permissions_smoke
import api_auth_smoke


class SalesApiTest(permissions_smoke.PermissionFlowTest):
    def prepare_sales(self, actions=('view', 'create', 'update', 'delete')):
        self.prepare_permissions()
        group = self.new_group()
        self.grant(group, ['sales.' + action for action in actions])
        self.assign(group)
        self.sales_group = group
        return group

    def sales(self, suffix='', method='GET', data=None, csrf=True):
        token = self.tokens()['sales'] if csrf and method != 'GET' else None
        return self.product_request('/api/sales/cart' + suffix, method, data, token)

    def sell_product(self, price='0.10'):
        with self.admin_session():
            return self.create_product(sale_price=price, cost_price='0.00', barcode='000' + secrets.token_hex(8))

    def scan(self, product):
        return self.sales('/items', 'POST', {'barcode': product['barcode']})

    def test_sales_repeated_scans_and_different_products(self):
        self.prepare_sales()
        first, second = self.sell_product(), self.sell_product('0.20')
        for _ in range(3):
            status, result = self.scan(first)
            self.assertEqual(status, 200)
        status, result = self.scan(second)
        self.assertEqual(status, 200)
        cart = result['data']
        self.assertEqual(cart['line_count'], 2)
        self.assertEqual(cart['quantity'], 4)
        self.assertEqual(cart['total'], '0.50')
        lines = {line['product_id']: line for line in cart['items']}
        self.assertEqual(lines[first['id']]['quantity'], 3)
        self.assertEqual(lines[first['id']]['subtotal'], '0.30')
        self.assertEqual(lines[first['id']]['barcode'], first['barcode'])
        self.assertEqual(self.sales()[1]['data']['total'], '0.50')
        self.assertEqual(self.product_request('/api/products')[0], 403)

    def test_sales_product_image_with_sales_permissions_only(self):
        group = self.prepare_sales()
        product = self.sell_product()
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        self.assertIsNone(self.scan(product)[1]['data']['items'][0]['image_url'])
        urls = []
        for _ in range(2):
            with self.admin_session():
                status, result = self.image_request(f'/api/products/{product["id"]}', {'name': product['name'], 'barcode': product['barcode'], 'sale_price': product['sale_price'], 'cost_price': product['cost_price']}, png, self.tokens()['products'])
                self.assertEqual(status, 200, result)
            url = self.sales()[1]['data']['items'][0]['image_url']
            urls.append(url)
            with self.client.open(api_auth_smoke.BASE_URL + url) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertEqual(response.read(), png)
            self.assertEqual(self.product_request('/api/products')[0], 403)
        self.assertNotEqual(*urls)
        self.grant(group, [])
        self.assertEqual(self.product_request(urls[-1])[0], 403)

    def test_sales_cart_preserves_scan_order(self):
        self.prepare_sales()
        first, second = self.sell_product(), self.sell_product()
        self.scan(second)
        self.scan(first)
        self.scan(second)
        lines = self.sales()[1]['data']['items']
        self.assertEqual([line['product_id'] for line in lines], [second['id'], first['id']])
        self.assertEqual(lines[0]['quantity'], 2)

    def test_sales_quantity_remove_and_clear(self):
        self.prepare_sales()
        first, second = self.sell_product('12.35'), self.sell_product('5.00')
        self.scan(first)
        self.scan(second)
        status, result = self.sales(f'/items/{first["id"]}', 'PATCH', {'quantity': 3})
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['total'], '42.05')
        status, result = self.sales(f'/items/{second["id"]}', 'DELETE')
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['quantity'], 3)
        self.assertEqual(result['data']['total'], '37.05')
        status, result = self.sales(method='DELETE')
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['items'], [])
        self.assertEqual(result['data']['total'], '0.00')

    def test_sales_permissions_are_independent(self):
        group = self.prepare_sales(('view', 'create'))
        product = self.sell_product()
        self.assertEqual(self.scan(product)[0], 200)
        self.assertEqual(self.scan(product)[0], 200)
        path = f'/items/{product["id"]}'
        self.assertEqual(self.sales(path, 'PATCH', {'quantity': 3})[0], 403)
        self.assertEqual(self.sales(path, 'DELETE')[0], 403)
        self.grant(group, ['sales.view', 'sales.update'])
        self.assertEqual(self.scan(product)[0], 403)
        self.assertEqual(self.sales(path, 'PATCH', {'quantity': 3})[0], 200)
        self.grant(group, ['sales.view', 'sales.delete'])
        self.assertEqual(self.sales(path, 'PATCH', {'quantity': 4})[0], 403)
        self.assertEqual(self.sales(path, 'DELETE')[0], 200)
        self.grant(group, [])
        self.assertEqual(self.sales()[0], 403)

    def test_sales_csrf_and_invalid_inputs_leave_cart_unchanged(self):
        self.prepare_sales()
        product = self.sell_product()
        self.assertEqual(self.sales('/items', 'POST', {'barcode': product['barcode']}, csrf=False)[0], 403)
        for data in [{'barcode': 123}, {'barcode': ''}, {'barcode': product['barcode'], 'unit_price': '0.00'}]:
            self.assertEqual(self.sales('/items', 'POST', data)[0], 422)
        status, result = self.sales('/items', 'POST', {'barcode': 'unknown_' + secrets.token_hex(8)})
        self.assertEqual(status, 404)
        self.assertIn('código de barras', result['error'])
        self.assertEqual(self.sales()[1]['data']['quantity'], 0)
        self.scan(product)
        for value in [0, -1, 10000, '2', 1.5, None]:
            self.assertEqual(self.sales(f'/items/{product["id"]}', 'PATCH', {'quantity': value})[0], 422)
        self.assertEqual(self.sales()[1]['data']['quantity'], 1)
        self.assertEqual(self.sales(method='DELETE', csrf=False)[0], 403)

    def test_sales_prices_come_from_catalog_and_deleted_products_are_removed(self):
        self.prepare_sales()
        product = self.sell_product()
        self.scan(product)
        with self.admin_session():
            status, _ = self.product_request(f'/api/products/{product["id"]}', 'PATCH', {'sale_price': '0.99'}, self.tokens()['products'])
            self.assertEqual(status, 200)
        self.assertEqual(self.sales()[1]['data']['total'], '0.99')
        with self.admin_session():
            self.assertEqual(self.product_request(f'/api/products/{product["id"]}', 'DELETE', csrf=self.tokens()['products'])[0], 204)
        cart = self.sales()[1]['data']
        self.assertEqual(cart['items'], [])
        self.assertTrue(cart['removed_unavailable'])
        self.assertFalse(self.sales()[1]['data']['removed_unavailable'])

    def test_sales_cart_isolated_by_user_and_logout_clears_it(self):
        self.prepare_sales()
        product = self.sell_product()
        self.scan(product)
        self.login()
        self.assertEqual(self.sales()[1]['data']['quantity'], 0)
        self.login(self.username, self.password)
        self.assertEqual(self.sales()[1]['data']['quantity'], 1)
        self.assertEqual(self.request('/api/logout', {'_csrf_token': self.tokens()['logout']}, form=True)[0], 200)
        self.login(self.username, self.password)
        self.assertEqual(self.sales()[1]['data']['quantity'], 0)

    def test_sales_max_quantity_uses_exact_money(self):
        self.prepare_sales()
        product = self.sell_product('9999999999.99')
        self.scan(product)
        status, result = self.sales(f'/items/{product["id"]}', 'PATCH', {'quantity': 9999})
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['total'], '99989999999900.01')
        self.assertEqual(self.scan(product)[0], 422)
        self.assertEqual(self.sales()[1]['data']['quantity'], 9999)


if __name__ == '__main__':
    unittest.main(verbosity=2)
