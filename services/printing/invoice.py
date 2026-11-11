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
# ESC p: drawer connector pin 2, 100 ms on / 500 ms off.
OPEN_CASH_DRAWER = b'\x1bp\x00\x32\xfa'


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


def payment_row(label, value):
    formatted = money(value)
    if len(label) + len(formatted) + 1 > WIDTH:
        return [label, formatted.rjust(WIDTH)]
    return [label + formatted.rjust(WIDTH - len(label))]


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
    lines.extend(['-' * WIDTH, *payment_row('TOTAL COP', total), '-' * WIDTH])
    received, change = invoice.get('cash_received'), invoice.get('change_due')
    method = invoice.get('payment_method')
    transferred = invoice.get('transfer_received')
    if method is not None and method not in ('cash', 'transfer', 'mixed'):
        raise ValueError('Metodo de pago no valido.')
    if transferred is not None:
        transferred = amount(transferred)
        # Older transfer-only invoices did not store cash/change values.
        received = Decimal('0') if method == 'transfer' and received is None else amount(received)
        change = Decimal('0') if method == 'transfer' and change is None else amount(change)
        expected_method = 'cash' if transferred == 0 else ('transfer' if received == 0 else 'mixed')
        if method != expected_method or transferred > total or received + transferred - total != change:
            raise ValueError('Los importes de efectivo y transferencia no coinciden con la factura.')
        lines.append('PAGO: ' + {'cash': 'EFECTIVO', 'transfer': 'TRANSFERENCIA', 'mixed': 'EFECTIVO Y TRANSFERENCIA'}[method])
        if method != 'transfer':
            lines.extend(payment_row('EFECTIVO RECIBIDO COP', received))
        lines.extend(payment_row('TRANSFERENCIA COP', transferred))
        if method != 'transfer':
            lines.extend(payment_row('CAMBIO COP', change))
    else:
        # Preserve compatibility with already queued and historical invoices.
        if method == 'mixed':
            raise ValueError('Falta el importe transferido.')
        if method == 'transfer':
            if received is not None or change is not None:
                raise ValueError('Una transferencia no recibe efectivo ni genera cambio.')
            lines.append('PAGO: TRANSFERENCIA')
            lines.extend(payment_row('TRANSFERENCIA COP', total))
        elif method == 'cash':
            if received is None or change is None:
                raise ValueError('Faltan los datos de efectivo.')
            lines.append('PAGO: EFECTIVO')
        if received is not None or change is not None:
            received, change = amount(received), amount(change)
            if received < total or received - total != change:
                raise ValueError('Dinero recibido o cambio no válido.')
            lines.extend(payment_row('EFECTIVO RECIBIDO COP', received))
            lines.extend(payment_row('CAMBIO COP', change))
    lines.extend(['-' * WIDTH, 'Gracias por su compra'.center(WIDTH)])
    # Queue the pulse after printing and cutting, in the same deduplicated job.
    return job_id, b'\x1b@' + ('\n'.join(lines) + '\n\n\n\n').encode('ascii') + b'\x1dV\x01' + OPEN_CASH_DRAWER


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
