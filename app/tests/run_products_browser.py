"""Ejecutar desde el host: python3 app/tests/run_products_browser.py.

Construye un entorno de pruebas aislado y crea un usuario/grupo temporales.
PRODUCTS_BROWSER_CONTAINER permite reutilizar un contenedor de pruebas preparado.
"""
import os
from pathlib import Path
import secrets
import subprocess

import api_auth_smoke

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'rg-licoreria-browser-tests:local'


class BrowserFixture(api_auth_smoke.ApiAuthenticationTest):
    pass


def main():
    container = os.environ.get('PRODUCTS_BROWSER_CONTAINER')
    if not container:
        subprocess.run(['docker', 'build', '-f', 'app/tests/browser.Dockerfile', '-t', IMAGE, 'app/tests'], cwd=ROOT, check=True)
    BrowserFixture.username = 'browser_smoke_' + secrets.token_hex(8)
    BrowserFixture.password = secrets.token_hex(16)
    BrowserFixture.fixture('create')
    try:
        credentials = ['-e', f'SMOKE_USERNAME={BrowserFixture.username}', '-e', f'SMOKE_PASSWORD={BrowserFixture.password}']
        if container:
            command = ['docker', 'exec', *credentials, container, 'python', '/tests/products_browser.py']
        else:
            command = ['docker', 'run', '--rm', '--network', 'host', *credentials,
                       '-v', f'{ROOT / "app/tests"}:/tests:ro', IMAGE]
        return subprocess.run(command, cwd=ROOT).returncode
    finally:
        BrowserFixture.fixture('delete')


if __name__ == '__main__':
    raise SystemExit(main())
