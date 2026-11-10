"""Pruebas HTTP contra el monolito local: python3 app/tests/api_auth_smoke.py."""
import http.cookiejar
import json
from pathlib import Path
import secrets
import subprocess
import unittest
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "http://localhost"


class ApiAuthenticationTest(unittest.TestCase):
    @classmethod
    def fixture(cls, action):
        code = r'''<?php
require 'vendor/autoload.php';
(new Symfony\Component\Dotenv\Dotenv())->bootEnv('.env');
$kernel = new App\Kernel($_ENV['APP_ENV'], true);
$kernel->boot();
$em = $kernel->getContainer()->get('doctrine')->getManager();
$username = getenv('SMOKE_USERNAME');
if (getenv('SMOKE_ACTION') === 'create') {
    $group = new App\Entity\UserGroup($username);
    $view = $em->getRepository(App\Entity\Permission::class)->findOneBy(['module' => 'products', 'action' => 'view']);
    $group->replacePermissions([$view]);
    $em->persist($group);
    $user = new App\Entity\User($username, [App\Entity\User::ROLE_USER]);
    $user->setGroup($group);
    $user->setPassword(password_hash(getenv('SMOKE_PASSWORD'), PASSWORD_BCRYPT));
    $em->persist($user);
} else {
    $user = $em->getRepository(App\Entity\User::class)->findOneBy(['username' => $username]);
    if ($user) {
        $em->createQuery('DELETE FROM App\Entity\Invoice i WHERE i.createdBy = :id')->setParameter('id', $user->getId())->execute();
        $em->remove($user);
    }
    $em->flush();
    $group = $em->getRepository(App\Entity\UserGroup::class)->findOneBy(['name' => $username]);
    if ($group) $em->remove($group);
}
$em->flush();
'''
        subprocess.run(
            ["docker", "compose", "--env-file", "app/.env.local", "exec", "-T",
             "-e", f"SMOKE_USERNAME={cls.username}", "-e", f"SMOKE_PASSWORD={cls.password}",
             "-e", f"SMOKE_ACTION={action}", "php", "php"],
            cwd=ROOT, input=code, text=True, check=True, capture_output=True,
        )

    @classmethod
    def setUpClass(cls):
        cls.username = "smoke_" + secrets.token_hex(8)
        cls.password = secrets.token_hex(16)
        cls.addClassCleanup(cls.fixture, "delete")
        cls.fixture("create")

    def setUp(self):
        self.cookies = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def request(self, path, data=None, *, raw=None, form=False):
        headers = {"Accept": "application/json"}
        body = raw
        if data is not None:
            if form:
                body = urllib.parse.urlencode(data).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(data).encode()
                headers["Content-Type"] = "application/json"
        request = urllib.request.Request(BASE_URL + path, data=body, headers=headers)
        try:
            response = self.client.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        self.assertIn("application/json", response.headers.get("Content-Type", ""))
        return response.status, json.loads(response.read())

    def tokens(self):
        status, data = self.request("/api/csrf")
        self.assertEqual(status, 200)
        return data

    def login(self, username="admin", password="admin"):
        return self.request("/api/login", {
            "username": username, "password": password,
            "_csrf_token": self.tokens()["login"],
        })

    def test_anonymous_requests_return_json_401(self):
        for path in ["/api/me", "/api/admin"]:
            self.assertEqual(self.request(path)[0], 401)

    def test_admin_login_and_access(self):
        status, data = self.login()
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["username"], "admin")
        self.assertEqual(set(data["user"]["roles"]), {"ROLE_ADMIN", "ROLE_USER"})
        self.assertNotIn("password", data["user"])
        self.assertEqual(self.request("/api/me")[0], 200)
        self.assertEqual(self.request("/api/admin")[0], 200)

    def test_invalid_credentials(self):
        status, wrong_password = self.login(password="incorrect-password")
        self.assertEqual(status, 401)
        status, unknown_user = self.login(username="unknown_" + secrets.token_hex(8))
        self.assertEqual(status, 401)
        self.assertEqual(wrong_password, unknown_user)
        self.assertEqual(self.request("/api/me")[0], 401)

    def test_login_requires_csrf(self):
        self.assertEqual(self.request("/api/login", {"username": "admin", "password": "admin"})[0], 401)
        self.assertEqual(self.request("/api/me")[0], 401)

    def test_invalid_payloads_return_json(self):
        for payload in [b'{invalid', b'[]', b'null']:
            self.assertEqual(self.request("/api/login", raw=payload)[0], 401)
        self.assertEqual(self.request("/api/login", {"username": [], "password": []})[0], 401)

    def test_user_cannot_access_admin(self):
        status, data = self.login(self.username, self.password)
        self.assertEqual(status, 200)
        self.assertEqual(data["user"]["roles"], ["ROLE_USER"])
        self.assertEqual(self.request("/api/me")[0], 200)
        self.assertEqual(self.request("/api/admin")[0], 403)

    def test_logout_requires_csrf_and_invalidates_session(self):
        self.assertEqual(self.login()[0], 200)
        self.assertEqual(self.request("/api/logout", {}, form=True)[0], 403)
        self.assertEqual(self.request("/api/me")[0], 200)
        status, data = self.request("/api/logout", {"_csrf_token": self.tokens()["logout"]}, form=True)
        self.assertEqual(status, 200)
        self.assertIn("message", data)
        self.assertEqual(self.request("/api/me")[0], 401)

    def test_frontend_and_assets_are_available(self):
        for path in ["/login", "/", "/admin", "/scripts/app.js", "/styles/app.css"]:
            with self.client.open(BASE_URL + path, timeout=10) as response:
                self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
