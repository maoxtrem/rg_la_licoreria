"""Run the billing browser flow with disposable invoices and company data."""
import os
import secrets
import subprocess

import api_auth_smoke
import run_products_browser
from company_smoke import CompanyApiTest


def main():
    fixture = CompanyApiTest()
    fixture.setUp()
    fixture.login()
    company_name = None
    if fixture.product_request('/api/company')[1]['data'] is None:
        company_name = 'billing_browser_' + secrets.token_hex(8)
        fixture.product_request('/api/company', 'POST', {'name': company_name, 'address': 'Calle de prueba', 'phone': '1234567', 'nit': '000-0'}, fixture.tokens()['company'])
    os.environ['BROWSER_TEST_FILE'] = 'billing_browser.py'
    try:
        return run_products_browser.main()
    finally:
        if company_name:
            fixture.remove_test_company(company_name)
        fixture.doCleanups()


if __name__ == '__main__':
    raise SystemExit(main())
