"""API de productos y regresión de login: python3 app/tests/products_smoke.py."""
import json
import secrets
import unittest
import urllib.error
import urllib.request

import api_auth_smoke


class ProductApiTest(api_auth_smoke.ApiAuthenticationTest):
    def setUp(self):
        super().setUp()
        self.created = []
        self.addCleanup(self.cleanup_products)

    def cleanup_products(self):
        if not self.created:
            return
        self.assertEqual(self.login()[0], 200)
        token = self.tokens()["products"]
        for product_id in self.created:
            status, _ = self.product_request(f"/api/products/{product_id}", "DELETE", csrf=token)
            self.assertIn(status, (204, 404))

    def product_request(self, path="/api/products", method="GET", data=None, csrf=None, raw=None):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if csrf is not None:
            headers["X-CSRF-Token"] = csrf
        body = json.dumps(data).encode() if data is not None else raw
        request = urllib.request.Request(api_auth_smoke.BASE_URL + path, data=body, method=method, headers=headers)
        try:
            response = self.client.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        content = response.read()
        if response.status == 204:
            self.assertEqual(content, b"")
            return response.status, None
        self.assertIn("application/json", response.headers.get("Content-Type", ""))
        return response.status, json.loads(content)

    def create_product(self, **changes):
        data = {"name": "Producto de prueba", "barcode": "000" + secrets.token_hex(10),
                "sale_price": "12500.5", "cost_price": "8000.00"}
        data.update(changes)
        status, result = self.product_request(method="POST", data=data, csrf=self.tokens()["products"])
        self.assertEqual(status, 201, result)
        self.created.append(result["data"]["id"])
        return result["data"]

    def test_product_crud_and_exact_prices(self):
        self.login()
        product = self.create_product()
        self.assertTrue(product["barcode"].startswith("000"))
        self.assertEqual(product["sale_price"], "12500.50")
        path = f'/api/products/{product["id"]}'
        self.assertEqual(self.product_request(path), (200, {"data": product}))
        status, listing = self.product_request()
        self.assertEqual(status, 200)
        self.assertIn(product, listing["data"])
        token = self.tokens()["products"]
        status, result = self.product_request(path, "PATCH", {"cost_price": "0.10"}, token)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["sale_price"], "12500.50")
        self.assertEqual(result["data"]["cost_price"], "0.10")
        self.assertEqual(result["data"]["name"], product["name"])
        replacement = {"name": "Producto actualizado", "barcode": product["barcode"],
                       "sale_price": "9999999999.99", "cost_price": 0}
        status, result = self.product_request(path, "PUT", replacement, token)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["sale_price"], "9999999999.99")
        self.assertEqual(result["data"]["cost_price"], "0.00")
        self.assertEqual(self.product_request(path, "DELETE", csrf=token)[0], 204)
        self.assertEqual(self.product_request(path)[0], 404)

    def test_product_validation(self):
        self.login()
        token = self.tokens()["products"]
        status, result = self.product_request(method="POST", data={}, csrf=token)
        self.assertEqual(status, 422)
        self.assertEqual(set(result["errors"]), {"name", "barcode", "sale_price", "cost_price"})
        data = {"name": "Prueba", "barcode": "validation", "sale_price": "10.00", "cost_price": "5.00"}
        for change, field in [({"sale_price": "-1"}, "sale_price"), ({"cost_price": "1.001"}, "cost_price"),
                              ({"sale_price": 0.1}, "sale_price"), ({"cost_price": "10000000000"}, "cost_price"),
                              ({"name": " "}, "name"), ({"barcode": 1234}, "barcode"),
                              ({"name": "n" * 181}, "name"), ({"stock": 10}, "stock")]:
            with self.subTest(change=change):
                status, result = self.product_request(method="POST", data=data | change, csrf=token)
                self.assertEqual(status, 422)
                self.assertIn(field, result["errors"])

    def test_duplicate_barcode_create_and_update(self):
        self.login()
        first = self.create_product()
        second = self.create_product()
        token = self.tokens()["products"]
        status, result = self.product_request(method="POST", data={key: value for key, value in first.items() if key != "id"}, csrf=token)
        self.assertEqual(status, 409)
        self.assertIn("barcode", result["errors"])
        path = f'/api/products/{second["id"]}'
        status, _ = self.product_request(path, "PATCH", {"barcode": first["barcode"]}, token)
        self.assertEqual(status, 409)
        self.assertEqual(self.product_request(path)[1]["data"]["barcode"], second["barcode"])

    def test_user_can_read_but_cannot_modify_products(self):
        self.login()
        product = self.create_product()
        path = f'/api/products/{product["id"]}'
        self.assertEqual(self.login(self.username, self.password)[0], 200)
        token = self.tokens()["products"]
        self.assertEqual(self.product_request()[0], 200)
        self.assertEqual(self.product_request(path)[0], 200)
        for target, method, data in [("/api/products", "POST", {}), (path, "PATCH", {"name": "Otro"}), (path, "DELETE", None)]:
            self.assertEqual(self.product_request(target, method, data, token)[0], 403)

    def test_product_mutations_require_csrf(self):
        self.login()
        product = self.create_product()
        path = f'/api/products/{product["id"]}'
        for target, method, data in [("/api/products", "POST", {}), (path, "PATCH", {"name": "Otro"}), (path, "DELETE", None)]:
            self.assertEqual(self.product_request(target, method, data)[0], 403)
        self.assertEqual(self.product_request(path)[1]["data"], product)

    def test_product_requests_require_authentication(self):
        for method in ["GET", "POST", "DELETE"]:
            path = "/api/products/1" if method == "DELETE" else "/api/products"
            self.assertEqual(self.product_request(path, method)[0], 401)

    def test_product_bad_json_and_pagination(self):
        self.login()
        token = self.tokens()["products"]
        for raw in [b"{invalid", b"[]", b"null"]:
            self.assertEqual(self.product_request(method="POST", raw=raw, csrf=token)[0], 400)
        for query in ["page=0", "limit=101", "page=foo", "limit=0", "page[]=1"]:
            self.assertEqual(self.product_request("/api/products?" + query)[0], 400)
        status, result = self.product_request("/api/products?page=1&limit=1")
        self.assertEqual(status, 200)
        self.assertLessEqual(len(result["data"]), 1)
        self.assertEqual(result["pagination"]["limit"], 1)

    def test_sidebar_routes_and_groups(self):
        for path in ["/productos", "/ventas", "/inventario", "/grupos", "/usuarios", "/permisos"]:
            with self.client.open(api_auth_smoke.BASE_URL + path) as response:
                html = response.read().decode()
                self.assertEqual(response.status, 200)
                self.assertIn('aria-label="Menú principal"', html)
                self.assertIn("Operativos", html)
                self.assertIn("Administrativos", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
