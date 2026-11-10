"""Internal printing receiver. Rendering and printer dispatch are future stages."""
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from uuid import uuid4
from printer import SatPrinter
from invoice import dispatch_invoice

LOGGER = logging.getLogger('printing')
MAX_BODY = 1024 * 1024


def reject_constant(value):
    raise ValueError('JSON constants must be finite')


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('JSON number is not finite')
    return number


class PrintingServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, spool_directory):
        self.spool_directory = Path(spool_directory)
        self.spool_directory.mkdir(parents=True, exist_ok=True)
        self.printer = SatPrinter()
        self.invoice_lock = threading.Lock()
        super().__init__(address, PrintingHandler)


class PrintingHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def respond(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/printer':
            self.respond(200, self.server.printer.status())
            return
        if self.path != '/health':
            self.respond(404, {'error': 'Recurso no encontrado.'})
            return
        if not os.access(self.server.spool_directory, os.W_OK):
            self.respond(503, {'status': 'unavailable'})
            return
        self.respond(200, {'status': 'ok', 'service': 'printing'})

    def do_POST(self):
        if self.path != '/print':
            self.respond(404, {'error': 'Recurso no encontrado.'})
            return
        if self.headers.get_content_type() != 'application/json':
            self.respond(415, {'error': 'Usa Content-Type: application/json.'})
            return
        lengths = self.headers.get_all('Content-Length', [])
        if not lengths:
            self.respond(411, {'error': 'Content-Length es obligatorio.'})
            return
        if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
            self.respond(400, {'error': 'Solicitud no válida.'})
            return
        try:
            length = int(lengths[0])
        except ValueError:
            length = -1
        if length < 1 or length > MAX_BODY:
            self.respond(413, {'error': 'El JSON debe ocupar entre 1 byte y 1 MiB.'})
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete request')
            payload = json.loads(raw.decode('utf-8'), parse_constant=reject_constant, parse_float=finite_float)
        except (ValueError, UnicodeError, TimeoutError, RecursionError):
            self.respond(400, {'error': 'El cuerpo debe ser un JSON válido en UTF-8.'})
            return
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), dict):
            self.respond(422, {'error': 'El JSON debe incluir data como objeto.'})
            return
        if set(payload) - {'data', 'template'}:
            self.respond(422, {'error': 'Solo se admiten data y, opcionalmente, template.'})
            return
        template = payload.get('template')
        if template is not None and (not isinstance(template, str) or not template.strip() or len(template) > 100):
            self.respond(422, {'error': 'template debe ser un nombre de entre 1 y 100 caracteres.'})
            return
        if template == 'invoice':
            try:
                status, result = dispatch_invoice(self.server, payload['data'])
            except (ValueError, KeyError, TypeError, OverflowError, UnicodeError):
                self.respond(422, {'error': 'Los datos de la factura no son válidos.'})
                return
            except OSError:
                LOGGER.exception('Could not persist an invoice print job')
                self.respond(503, {'error': 'No se pudo guardar el estado de impresión.'})
                return
            self.respond(status, result)
            return
        job_id = str(uuid4())
        job = {'id': job_id, 'status': 'received', 'created_at': datetime.now(timezone.utc).isoformat(),
               'template': template, 'data': payload['data']}
        try:
            encoded_job = json.dumps(job, ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (ValueError, UnicodeError, RecursionError):
            self.respond(422, {'error': 'Los datos contienen valores que no se pueden guardar como JSON UTF-8.'})
            return
        temporary = None
        try:
            # Publish a complete file atomically. Acknowledgement follows durable storage.
            with tempfile.NamedTemporaryFile(mode='wb', dir=self.server.spool_directory,
                                             prefix='.incoming-', delete=False) as output:
                temporary = Path(output.name)
                output.write(encoded_job)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self.server.spool_directory / (job_id + '.json'))
            temporary = None
            directory_fd = os.open(self.server.spool_directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            LOGGER.exception('Could not store a printing request')
            self.respond(503, {'error': 'No se pudo guardar la solicitud. Inténtalo nuevamente.'})
            return
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        LOGGER.info('Request received: %s', job_id)
        self.respond(202, {'id': job_id, 'status': 'received'})

    def log_message(self, format, *args):
        # Never log the request body, which may later contain customer data.
        LOGGER.info('%s %s', self.address_string(), format % args)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    server = PrintingServer(('0.0.0.0', 8080), os.environ.get('PRINT_SPOOL_DIR', '/data'))
    LOGGER.info('Printing receiver listening on port 8080')
    server.serve_forever()
