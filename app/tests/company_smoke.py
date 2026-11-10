"""Empresa y regresión de autorización: python3 app/tests/company_smoke.py."""
import secrets
import subprocess
import unittest

import api_auth_smoke
from permissions_smoke import PermissionFlowTest


class CompanyApiTest(PermissionFlowTest):
    def remove_test_company(self, name):
        code = r'''<?php
require 'vendor/autoload.php';
(new Symfony\Component\Dotenv\Dotenv())->bootEnv('.env');
$kernel = new App\Kernel($_ENV['APP_ENV'], true);
$kernel->boot();
$em = $kernel->getContainer()->get('doctrine')->getManager();
$company = $em->find(App\Entity\Company::class, 1);
if ($company && $company->toArray()['name'] === getenv('SMOKE_COMPANY_NAME')) {
    $em->remove($company);
    $em->flush();
}
'''
        subprocess.run(['docker', 'compose', '--env-file', 'app/.env.local', 'exec', '-T',
                        '-e', f'SMOKE_COMPANY_NAME={name}', 'php', 'php'],
                       cwd=api_auth_smoke.ROOT, input=code, text=True, check=True, capture_output=True)

    def test_company_create_read_update_and_validation(self):
        self.assertEqual(self.product_request('/api/company')[0], 401)
        self.login()
        status, initial = self.product_request('/api/company')
        self.assertEqual(status, 200)
        if initial['data'] is not None:
            self.skipTest('La empresa ya está configurada; se conservan sus datos.')
        name = 'company_smoke_' + secrets.token_hex(8)
        values = {'name': name, 'address': 'Calle 10 # 20-30', 'phone': '+57 001234567', 'nit': '001234567-8'}
        token = self.tokens()['company']
        self.assertEqual(self.product_request('/api/company', 'PATCH', {'phone': '123'}, token)[0], 404)
        self.addCleanup(self.remove_test_company, name)
        status, result = self.product_request('/api/company', 'POST', values, token)
        self.assertEqual(status, 201, result)
        self.assertEqual(result['data'], values)
        self.assertEqual(self.product_request('/api/company'), (200, {'data': values}))
        self.assertEqual(self.product_request('/api/company', 'POST', values, token)[0], 409)
        status, result = self.product_request('/api/company', 'PATCH', {'phone': '+57 000765432'}, token)
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['nit'], values['nit'])
        self.assertEqual(result['data']['phone'], '+57 000765432')
        for data in [{}, {'phone': 123}, {'nit': None}, {'address': 'x' * 256}, {'name': '  '}, {'name': 'A\x1b@'}, {'name': 'A\nB'}, {'unknown': 'value'}]:
            self.assertEqual(self.product_request('/api/company', 'PATCH', data, token)[0], 422, data)
        self.assertEqual(self.product_request('/api/company', 'PUT', {'name': name}, token)[0], 422)
        values['address'] = 'Carrera 7 # 10-20'
        self.assertEqual(self.product_request('/api/company', 'PUT', values, token), (200, {'data': values}))
        self.assertEqual(self.product_request('/api/company', 'DELETE', csrf=token)[0], 405)

    def test_company_csrf_and_input(self):
        self.login()
        self.assertEqual(self.product_request('/api/company', 'POST', {})[0], 403)
        self.assertEqual(self.product_request('/api/company', 'PATCH', {})[0], 403)
        token = self.tokens()['company']
        for raw in [b'{broken', b'[]']:
            self.assertEqual(self.product_request('/api/company', 'POST', csrf=token, raw=raw)[0], 400)
        status, result = self.product_request('/api/company', 'POST', {}, token)
        self.assertEqual(status, 422)
        self.assertEqual(set(result['errors']), {'name', 'address', 'phone', 'nit'})

    def test_company_permissions_are_independent_and_revocable(self):
        self.prepare_permissions()
        group = self.new_group()
        self.assign(group)
        self.assertEqual(self.product_request('/api/company')[0], 403)
        self.grant(group, ['company.view'])
        self.assertEqual(self.product_request('/api/company')[0], 200)
        token = self.tokens()['company']
        self.assertEqual(self.product_request('/api/company', 'POST', {}, token)[0], 403)
        self.assertEqual(self.product_request('/api/company', 'PATCH', {}, token)[0], 403)
        self.grant(group, ['company.view', 'company.create'])
        self.assertEqual(self.product_request('/api/company', 'POST', {}, token)[0], 422)
        self.assertEqual(self.product_request('/api/company', 'PATCH', {}, token)[0], 403)
        self.grant(group, ['company.view', 'company.update'])
        self.assertIn(self.product_request('/api/company', 'PATCH', {}, token)[0], [404, 422])
        self.assertEqual(self.product_request('/api/company', 'POST', {}, token)[0], 403)
        self.assertEqual(self.product_request('/api/modules/billing/access')[0], 403)
        self.grant(group, [])
        self.assertEqual(self.product_request('/api/company')[0], 403)


if __name__ == '__main__':
    unittest.main(defaultTest='CompanyApiTest', verbosity=2)
