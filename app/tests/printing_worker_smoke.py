"""Redis -> Messenger worker -> real printing HTTP server -> simulated USB.

Uses an isolated Redis stream and temporary container/spool. No physical ticket.
"""
import json
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ['docker', 'compose', '--env-file', 'app/.env.local']


def command(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, text=True, check=True, capture_output=True, timeout=45, **kwargs)


def main():
    suffix = secrets.token_hex(8)
    name = 'printing-smoke-' + suffix
    stream = 'printing_smoke_' + suffix
    invoice = {'id': 1, 'number': 'F-PRUEBA', 'status': 'paid', 'paid_at': '2026-11-10T07:00:00+00:00',
               'company': {'name': 'Empresa de prueba', 'nit': '00123-4', 'address': 'Calle prueba', 'phone': '0012345'},
               'items': [{'product_id': 1, 'name': 'Producto', 'quantity': 2, 'unit_price': '10.25', 'subtotal': '20.50'}],
               'total': '20.50', 'payment_method': 'mixed', 'cash_received': '15.00', 'transfer_received': '10.00', 'change_due': '4.50'}
    server_code = '''
from pathlib import Path
from server import PrintingServer
class FakeUsb:
    def status(self): return {'connected': True}
    def write(self, payload):
        with open('/tmp/tickets', 'ab') as output: output.write(payload)
        with open('/tmp/write-count', 'a') as output: output.write('1\\n')
server = PrintingServer(('0.0.0.0', 8080), '/tmp/printing-smoke')
server.printer = FakeUsb()
server.serve_forever()
'''
    try:
        command(COMPOSE + ['run', '--rm', '-d', '--no-deps', '--name', name, 'printing', 'python', '-c', server_code])
        for attempt in range(20):
            ready = subprocess.run(['docker', 'exec', name, 'python', '-c', "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"], cwd=ROOT, capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.2)
        else:
            raise AssertionError('El servidor temporal no inició.')
        php = r'''<?php
require 'vendor/autoload.php';
(new Symfony\Component\Dotenv\Dotenv())->bootEnv('.env');
$kernel = new App\Kernel($_ENV['APP_ENV'], true); $kernel->boot();
$bus = $kernel->getContainer()->get('messenger.default_bus');
$message = new App\Message\PrintInvoice(getenv('SMOKE_JOB'), json_decode(getenv('SMOKE_INVOICE'), true));
$bus->dispatch($message);
$bus->dispatch($message);
'''
        command(COMPOSE + ['exec', '-T', '-e', f'MESSENGER_TRANSPORT_DSN=redis://redis:6379/{stream}',
                          '-e', 'SMOKE_JOB=' + suffix * 2, '-e', 'SMOKE_INVOICE=' + json.dumps(invoice), 'php', 'php'], input=php)
        consumed = command(COMPOSE + ['run', '--rm', '--no-deps', '-e', f'MESSENGER_TRANSPORT_DSN=redis://redis:6379/{stream}',
                                     '-e', f'MESSENGER_CONSUMER_NAME=smoke-{suffix}', '-e', f'PRINT_SERVICE_URL=http://{name}:8080',
                                     'worker', 'php', 'bin/console', 'messenger:consume', 'async', '--limit=2', '--time-limit=15', '-vv'])
        check = "import json; from pathlib import Path; p=Path('/tmp/printing-smoke'); jobs=list(p.glob('*.json')); assert len(jobs)==1; assert json.loads(jobs[0].read_text())['status']=='sent'; assert Path('/tmp/write-count').read_text().splitlines()==['1']; ticket=Path('/tmp/tickets').read_bytes(); assert b'RECIBIDO COP' in ticket and b'$15,00' in ticket; assert b'CAMBIO COP' in ticket and b'$4,50' in ticket; assert b'TRANSFERENCIA COP' in ticket and b'$10,00' in ticket; print('OK: 2 mensajes procesados por el worker, 1 ticket con recibido y cambio enviado por USB simulado.')"
        print(command(['docker', 'exec', name, 'python', '-c', check]).stdout.strip())
    finally:
        subprocess.run(['docker', 'rm', '-f', name], cwd=ROOT, capture_output=True)
        subprocess.run(COMPOSE + ['exec', '-T', 'redis', 'redis-cli', 'DEL', stream], cwd=ROOT, capture_output=True)


if __name__ == '__main__':
    main()
