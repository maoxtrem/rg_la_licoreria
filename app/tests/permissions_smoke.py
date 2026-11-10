"""Permisos por grupo y regresión completa: python3 app/tests/permissions_smoke.py."""
from contextlib import contextmanager
import http.cookiejar
import secrets
import unittest
import urllib.request

import products_smoke


class PermissionFlowTest(products_smoke.ProductApiTest):
    @contextmanager
    def admin_session(self):
        original = self.client
        self.client = self.admin_client
        try:
            yield
        finally:
            self.client = original

    def prepare_permissions(self):
        self.admin_client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with self.admin_session():
            self.assertEqual(self.login()[0], 200)
        status, login = self.login(self.username, self.password)
        self.assertEqual(status, 200)
        self.user_id = login['user']['id']
        self.original_group = login['user']['group']['id']
        self.groups = []
        self.addCleanup(self.cleanup_groups)

    def admin_api(self, path, method='GET', data=None, token_id=None):
        with self.admin_session():
            token = self.tokens()[token_id] if token_id else None
            return self.product_request(path, method, data, token)

    def cleanup_groups(self):
        status, _ = self.admin_api(f'/api/users/{self.user_id}/group', 'PUT', {'group_id': self.original_group}, 'users')
        self.assertEqual(status, 200)
        for group_id in self.groups:
            status, _ = self.admin_api(f'/api/groups/{group_id}', 'DELETE', token_id='groups')
            self.assertIn(status, (204, 404))

    def new_group(self):
        status, result = self.admin_api('/api/groups', 'POST', {'name': 'smoke_group_' + secrets.token_hex(8)}, 'groups')
        self.assertEqual(status, 201, result)
        group_id = result['data']['id']
        self.groups.append(group_id)
        return group_id

    def grant(self, group_id, keys):
        status, result = self.admin_api(f'/api/groups/{group_id}/permissions', 'PUT', {'permissions': keys}, 'permissions')
        self.assertEqual(status, 200, result)

    def assign(self, group_id):
        status, result = self.admin_api(f'/api/users/{self.user_id}/group', 'PUT', {'group_id': group_id}, 'users')
        self.assertEqual(status, 200, result)

    def test_permissions_no_group_denies_all_modules(self):
        self.prepare_permissions()
        self.assign(None)
        status, result = self.request('/api/me')
        self.assertEqual(status, 200)
        self.assertIsNone(result['user']['group'])
        self.assertTrue(all(not value for actions in result['user']['permissions'].values() for value in actions.values()))
        for module in ['products', 'sales', 'inventory', 'groups', 'users', 'permissions']:
            self.assertEqual(self.product_request(f'/api/modules/{module}/access')[0], 403)
        self.assertEqual(self.product_request()[0], 403)

    def test_permissions_group_grants_and_revokes_without_login(self):
        self.prepare_permissions()
        group = self.new_group()
        self.assign(group)
        self.assertEqual(self.product_request()[0], 403)
        self.grant(group, ['products.view'])
        self.assertEqual(self.product_request()[0], 200)
        self.assertTrue(self.request('/api/me')[1]['user']['permissions']['products']['view'])
        self.grant(group, [])
        self.assertEqual(self.product_request()[0], 403)
        self.assertFalse(self.request('/api/me')[1]['user']['permissions']['products']['view'])
        self.assertEqual(self.request('/api/me')[1]['user']['username'], self.username)

    def test_permissions_each_write_action_is_independent(self):
        self.prepare_permissions()
        group = self.new_group()
        self.assign(group)
        self.grant(group, ['products.view', 'products.create'])
        product = self.create_product()
        path = f'/api/products/{product["id"]}'
        token = self.tokens()['products']
        self.assertEqual(self.product_request(path, 'PATCH', {'name': 'Blocked'}, token)[0], 403)
        self.assertEqual(self.product_request(path, 'DELETE', csrf=token)[0], 403)
        self.grant(group, ['products.view', 'products.update'])
        self.assertEqual(self.product_request(method='POST', data={}, csrf=token)[0], 403)
        self.assertEqual(self.product_request(path, 'PATCH', {'name': 'Allowed'}, token)[0], 200)
        self.assertEqual(self.product_request(path, 'DELETE', csrf=token)[0], 403)
        self.grant(group, ['products.view', 'products.delete'])
        self.assertEqual(self.product_request(path, 'PATCH', {'name': 'Blocked'}, token)[0], 403)
        self.assertEqual(self.product_request(path, 'DELETE', csrf=token)[0], 204)

    def test_permissions_view_is_required_for_other_actions(self):
        self.prepare_permissions()
        group = self.new_group()
        for keys in [['products.create'], ['products.update'], ['products.delete'], ['products.view', 'groups.create']]:
            status, _ = self.admin_api(f'/api/groups/{group}/permissions', 'PUT', {'permissions': keys}, 'permissions')
            self.assertEqual(status, 422)
        self.assertEqual(self.admin_api(f'/api/groups/{group}')[1]['data']['permissions'], [])

    def test_permissions_admin_bypasses_all_groups(self):
        self.prepare_permissions()
        with self.admin_session():
            user = self.request('/api/me')[1]['user']
            self.assertIsNone(user['group'])
            self.assertTrue(all(value for actions in user['permissions'].values() for value in actions.values()))
            for module in user['permissions']:
                self.assertEqual(self.product_request(f'/api/modules/{module}/access')[0], 200)
            self.create_product()
        status, _ = self.admin_api(f'/api/users/{user["id"]}/group', 'PUT', {'group_id': self.original_group}, 'users')
        self.assertEqual(status, 422)

    def test_permissions_policy_assignments_are_admin_only(self):
        self.prepare_permissions()
        group = self.new_group()
        keys = [f'{module}.{action}' for module in ['products', 'groups', 'users', 'permissions'] for action in ['view', 'create', 'update', 'delete']]
        self.grant(group, keys)
        self.assign(group)
        for path, data, token in [
            (f'/api/groups/{group}/permissions', {'permissions': []}, 'permissions'),
            (f'/api/users/{self.user_id}/group', {'group_id': None}, 'users'),
        ]:
            self.assertEqual(self.product_request(path, 'PUT', data, self.tokens()[token])[0], 403)
        self.assertEqual(self.product_request('/api/permissions')[0], 200)
        self.assertEqual(self.product_request('/api/groups')[0], 200)
        self.assertEqual(self.product_request('/api/users')[0], 200)
        self.assertEqual(self.product_request('/api/admin')[0], 403)

    def test_permissions_unknown_grants_and_role_injection_are_rejected(self):
        self.prepare_permissions()
        group = self.new_group()
        for keys in [['ROLE_ADMIN'], ['products.fly'], ['unknown.view'], [12], 'products.view']:
            self.assertEqual(self.admin_api(f'/api/groups/{group}/permissions', 'PUT', {'permissions': keys}, 'permissions')[0], 422)
        self.assertEqual(self.admin_api(f'/api/users/{self.user_id}/group', 'PUT', {'group_id': group, 'roles': ['ROLE_ADMIN']}, 'users')[0], 422)
        self.assertEqual(self.admin_api('/api/groups', 'POST', {'name': 'Injection', 'permissions': ['products.view']}, 'groups')[0], 422)

    def test_permissions_group_crud_and_membership_protection(self):
        self.prepare_permissions()
        group = self.new_group()
        self.grant(group, ['products.view'])
        self.assign(group)
        self.assertEqual(self.admin_api(f'/api/groups/{group}', 'DELETE', token_id='groups')[0], 409)
        new_name = 'renamed_' + secrets.token_hex(8)
        status, result = self.admin_api(f'/api/groups/{group}', 'PATCH', {'name': new_name}, 'groups')
        self.assertEqual(status, 200)
        self.assertEqual(result['data']['permissions'], ['products.view'])
        self.assertEqual(self.admin_api('/api/groups', 'POST', {'name': new_name}, 'groups')[0], 409)
        self.assign(None)
        self.assertEqual(self.admin_api(f'/api/groups/{group}', 'DELETE', token_id='groups')[0], 204)
        self.assertEqual(self.admin_api(f'/api/groups/{group}')[0], 404)

    def test_permissions_isolation_between_modules_and_groups(self):
        self.prepare_permissions()
        first, second = self.new_group(), self.new_group()
        self.grant(first, ['sales.view'])
        self.grant(second, ['inventory.view'])
        self.assign(first)
        self.assertEqual(self.product_request('/api/modules/sales/access')[0], 200)
        self.assertEqual(self.product_request('/api/modules/inventory/access')[0], 403)
        self.assertEqual(self.product_request()[0], 403)
        self.assign(second)
        self.assertEqual(self.product_request('/api/modules/sales/access')[0], 403)
        self.assertEqual(self.product_request('/api/modules/inventory/access')[0], 200)

    def test_permissions_management_requires_csrf_and_catalog_is_fixed(self):
        self.prepare_permissions()
        status, result = self.admin_api('/api/permissions')
        self.assertEqual(status, 200)
        self.assertEqual(len(result['data']), 24)
        self.assertEqual(len({item['key'] for item in result['data']}), 24)
        self.assertEqual(self.admin_api('/api/groups', 'POST', {'name': 'NoCsrf'})[0], 403)
        self.assertEqual(self.admin_api('/api/permissions', 'POST', {})[0], 405)
        self.assertEqual(self.admin_api('/api/groups?page=0')[0], 400)
        self.assertEqual(self.admin_api('/api/users?limit=101')[0], 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
