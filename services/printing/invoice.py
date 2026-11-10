"""Invoice ESC/POS rendering and durable deduplication for Messenger redelivery."""
from datetime import datetime
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unicodedata
from zoneinfo import ZoneInfo

from printer import PrinterUnavailable
import usb.core

WIDTH = 42


def printable(value):
    if not isinstance(value, str) or len(value) > 255:
        raise ValueError('Texto de factura no válido.')
    # Never allow stored text to become an ESC/POS command.
    ascii_text = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    return ''.join(char if 32 <= ord(char) <= 126 else ' ' for char in ascii_text)


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,18}\.\d{2}', value):
        raise ValueError('Importe no válido.')
    return Decimal(value)


def money(value):
    return '$' + f'{value:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def render_invoice(data):
    job_id = data.get('print_job_id')
    invoice = data.get('invoice')
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id) or not isinstance(invoice, dict):
        raise ValueError('Referencia de impresión no válida.')
    if invoice.get('status') != 'paid' or not isinstance(invoice.get('id'), int) or invoice['id'] < 1:
        raise ValueError('Solo se imprimen facturas facturadas.')
    company = invoice.get('company')
    items = invoice.get('items')
    if not isinstance(company, dict) or not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise ValueError('Faltan los datos de empresa o los productos.')
    lines = []
    for field in ['name', 'nit', 'address', 'phone']:
        value = printable(company.get(field))
        prefix = {'nit': 'NIT: ', 'phone': 'Tel: '}.get(field, '')
        lines.extend(line.center(WIDTH) for line in textwrap.wrap(prefix + value, WIDTH))
    paid_at = datetime.fromisoformat(invoice['paid_at']).astimezone(ZoneInfo('America/Bogota'))
    lines.extend(['-' * WIDTH, 'FACTURA ' + printable(invoice.get('number')),
                  'Fecha: ' + paid_at.strftime('%Y-%m-%d %H:%M'), 'Estado: Pagada / Facturada', '-' * WIDTH])
    total = Decimal('0')
    for item in items:
        if not isinstance(item, dict) or type(item.get('quantity')) is not int or not 1 <= item['quantity'] <= 9999:
            raise ValueError('Cantidad no válida.')
        price = amount(item.get('unit_price'))
        subtotal = amount(item.get('subtotal'))
        if price * item['quantity'] != subtotal:
            raise ValueError('Subtotal no válido.')
        total += subtotal
        lines.extend(textwrap.wrap(printable(item.get('name')), WIDTH))
        detail = f"{item['quantity']} x {money(price)}"
        value = money(subtotal)
        if len(detail) + len(value) + 1 > WIDTH:
            lines.extend([detail, value.rjust(WIDTH)])
        else:
            lines.append(detail + value.rjust(WIDTH - len(detail)))
    if total != amount(invoice.get('total')):
        raise ValueError('Total no válido.')
    lines.extend(['-' * WIDTH, 'TOTAL COP', money(total).rjust(WIDTH), '-' * WIDTH, 'Gracias por su compra'.center(WIDTH)])
    return job_id, b'\x1b@' + ('\n'.join(lines) + '\n\n\n\n').encode('ascii') + b'\x1dV\x01'


def save_job(directory, job):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix='.invoice-', delete=False) as output:
            temporary = Path(output.name)
            output.write(json.dumps(job, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(directory / (job['id'] + '.json'))
        temporary = None
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def dispatch_invoice(server, data):
    job_id, ticket = render_invoice(data)
    # Thread lock plus flock covers concurrent requests and multiple processes.
    with server.invoice_lock, (server.spool_directory / '.invoice.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = server.spool_directory / (job_id + '.json')
        if path.exists():
            existing = json.loads(path.read_text())
            if existing.get('data') != data:
                return 409, {'error': 'La referencia corresponde a otra factura.'}
            if existing['status'] == 'sent':
                return 200, {'id': job_id, 'status': 'sent'}
            # A crash/write timeout might have happened after paper was printed.
            return 409, {'id': job_id, 'status': 'uncertain', 'error': 'Revisa la salida física antes de solicitar otra impresión.'}
        if not server.printer.status()['connected']:
            return 503, {'error': 'La impresora USB no está conectada.'}
        job = {'id': job_id, 'template': 'invoice', 'data': data, 'status': 'dispatching',
               'created_at': datetime.now(ZoneInfo('UTC')).isoformat()}
        save_job(server.spool_directory, job)
        try:
            server.printer.write(ticket)
        except (PrinterUnavailable, usb.core.USBError):
            job['status'] = 'uncertain'
            save_job(server.spool_directory, job)
            return 409, {'id': job_id, 'status': 'uncertain', 'error': 'Envío incierto; revisa la impresora antes de repetir.'}
        job['status'] = 'sent'
        save_job(server.spool_directory, job)
        return 200, {'id': job_id, 'status': 'sent'}
