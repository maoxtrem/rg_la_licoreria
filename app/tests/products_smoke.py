"""API de productos y regresión de login: python3 app/tests/products_smoke.py."""
import base64
import json
import secrets
import subprocess
import unittest
import urllib.error
import urllib.parse
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

    def image_request(self, path, data, image, csrf, filename="product.png"):
        boundary = "product-" + secrets.token_hex(16)
        raw = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"data\"\r\n\r\n".encode()
               + json.dumps(data).encode()
               + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\nContent-Type: image/png\r\n\r\n".encode()
               + image + f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(api_auth_smoke.BASE_URL + path, data=raw, headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Accept": "application/json", "X-CSRF-Token": csrf,
        })
        try:
            response = self.client.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        return response.status, json.loads(response.read())

    def assert_minio_image_exists(self, image_url, exists):
        filename = urllib.parse.parse_qs(urllib.parse.urlsplit(image_url).query)["v"][0]
        code = r'''<?php
require 'vendor/autoload.php';
(new Symfony\Component\Dotenv\Dotenv())->bootEnv('.env');
$client = new Aws\S3\S3Client([
    'version' => 'latest', 'region' => $_ENV['MINIO_REGION'],
    'endpoint' => $_ENV['MINIO_ENDPOINT'], 'use_path_style_endpoint' => true,
    'credentials' => ['key' => $_ENV['MINIO_ROOT_USER'], 'secret' => $_ENV['MINIO_ROOT_PASSWORD']],
]);
try {
    $client->headObject(['Bucket' => $_ENV['MINIO_BUCKET'], 'Key' => 'products/'.getenv('IMAGE_FILENAME')]);
    echo 'exists';
} catch (Aws\S3\Exception\S3Exception $exception) {
    if ($exception->getStatusCode() !== 404) throw $exception;
    echo 'missing';
}
'''
        result = subprocess.run([
            "docker", "compose", "--env-file", "app/.env.local", "exec", "-T",
            "-e", "IMAGE_FILENAME=" + filename, "php", "php",
        ], cwd=api_auth_smoke.ROOT, input=code, text=True, check=True, capture_output=True)
        self.assertEqual(result.stdout, "exists" if exists else "missing")

    def test_product_image_minio_lifecycle(self):
        self.login()
        token = self.tokens()["products"]
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
        data = {"name": "Con imagen", "barcode": "image-" + secrets.token_hex(10),
                "sale_price": "100.00", "cost_price": "50.00"}
        status, result = self.image_request("/api/products", data, png, token)
        self.assertEqual(status, 201, result)
        product = result["data"]
        self.created.append(product["id"])
        path = f'/api/products/{product["id"]}'
        self.assert_minio_image_exists(product["image_url"], True)
        with self.client.open(api_auth_smoke.BASE_URL + product["image_url"]) as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertEqual(response.read(), png)
        # Una edición sin archivo conserva la imagen almacenada.
        status, edited = self.product_request(path, "PATCH", {"name": "Renombrado"}, token)
        self.assertEqual(status, 200)
        self.assertEqual(edited["data"]["image_url"], product["image_url"])
        for image in (b"not an image", png + b"x" * (2 * 1024 * 1024)):
            status, invalid = self.image_request(path, data, image, token)
            self.assertEqual(status, 422, invalid)
            self.assertIn("image", invalid["errors"])
            self.assertEqual(self.product_request(path)[1]["data"]["image_url"], product["image_url"])
        self.assertEqual(self.image_request(path, data, png, "invalid")[0], 403)
        status, replaced = self.image_request(path, data, png, token)
        self.assertEqual(status, 200, replaced)
        self.assertNotEqual(replaced["data"]["image_url"], product["image_url"])
        self.assert_minio_image_exists(product["image_url"], False)
        self.assert_minio_image_exists(replaced["data"]["image_url"], True)
        self.login(self.username, self.password)
        with self.client.open(api_auth_smoke.BASE_URL + replaced["data"]["image_url"]) as response:
            self.assertEqual(response.read(), png)
        self.assertEqual(self.image_request(path, data, png, self.tokens()["products"])[0], 403)
        self.login()
        self.assertEqual(self.product_request(path, "DELETE", csrf=self.tokens()["products"])[0], 204)
        self.assertEqual(self.product_request(path + "/image")[0], 404)
        self.assert_minio_image_exists(replaced["data"]["image_url"], False)

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

    def test_barcode_filter(self):
        self.login()
        product = self.create_product(barcode="000+%&_" + secrets.token_hex(10))
        self.create_product()
        query = urllib.parse.urlencode({"barcode": " " + product["barcode"] + " ", "limit": 1})
        status, result = self.product_request("/api/products?" + query)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"], [product])
        self.assertEqual(result["pagination"], {"page": 1, "limit": 1, "total": 1})
        for barcode in (product["barcode"][1:], "missing-" + secrets.token_hex(10)):
            status, result = self.product_request("/api/products?" + urllib.parse.urlencode({"barcode": barcode}))
            self.assertEqual(status, 200)
            self.assertEqual(result["data"], [])
            self.assertEqual(result["pagination"]["total"], 0)
        self.assertEqual(self.product_request("/api/products?barcode[]=123")[0], 400)
        unfiltered = self.product_request()[1]
        self.assertEqual(self.product_request("/api/products?barcode=%20")[1], unfiltered)

    def test_duplicate_barcode_create_and_update(self):
        self.login()
        first = self.create_product()
        second = self.create_product()
        token = self.tokens()["products"]
        status, result = self.product_request(method="POST", data={key: value for key, value in first.items() if key not in ("id", "image_url")}, csrf=token)
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
