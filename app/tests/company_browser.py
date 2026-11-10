"""Formulario de empresa y permisos reales en Chromium, sin cambiar su ficha."""
import os
import unittest

from playwright.sync_api import expect
import products_browser


class CompanyBrowserTest(products_browser.ProductsBrowserTest):
    def test_company_form_and_revoked_access(self):
        self.grant(['company.view'])
        self.page.goto(products_browser.BASE + '/login')
        self.page.locator('#username').fill(os.environ['SMOKE_USERNAME'])
        self.page.locator('#password').fill(os.environ['SMOKE_PASSWORD'])
        self.page.locator('#login-button').click()
        self.page.wait_for_url(products_browser.BASE + '/')
        self.page.get_by_role('link', name='Empresa', exact=True).click()
        expect(self.page.locator('#company-form')).to_be_visible()
        expect(self.page.locator('#company-name')).to_be_disabled()
        expect(self.page.locator('#company-save')).to_be_hidden()
        expect(self.page.locator('#company-nit')).to_have_attribute('type', 'text')
        self.grant(['company.view', 'company.create', 'company.update'])
        self.page.locator('#company-refresh').click()
        expect(self.page.locator('#company-name')).to_be_enabled()
        expect(self.page.locator('#company-save')).to_be_visible()
        for field, value in {'name': 'Prueba sin guardar', 'address': 'Calle 1', 'phone': '0012345', 'nit': '00123-4'}.items():
            self.page.locator('#company-' + field).fill(value)
        self.grant([])
        self.page.locator('#company-save').click()
        expect(self.page.locator('#access-denied-view')).to_be_visible()
        expect(self.page.locator('#company-view')).to_be_hidden()
        expect(self.page.locator('#company-name')).to_have_value('')
        expect(self.page.get_by_role('link', name='Empresa', exact=True)).to_be_hidden()
        self.page.reload()
        expect(self.page.locator('#access-denied-view')).to_be_visible()


if __name__ == '__main__':
    unittest.main(defaultTest='CompanyBrowserTest.test_company_form_and_revoked_access', verbosity=2)
