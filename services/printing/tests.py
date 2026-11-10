import concurrent.futures
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import usb.core
from printer import SatPrinter, PrinterUnavailable
import urllib.error
import urllib.request

from server import MAX_BODY, PrintingServer


class PrintingTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = PrintingServer(('127.0.0.1', 0), self.directory.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path='/print', payload=None, raw=None, content_type='application/json'):
        body = json.dumps(payload).encode() if payload is not None else raw
        request = urllib.request.Request(self.url + path, data=body, headers={'Content-Type': content_type})
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        self.assertIn('application/json', response.headers['Content-Type'])
        return response.status, json.loads(response.read())

    def test_printer_status(self):
        with patch('printer.usb.core.find', return_value=None):
            status, result = self.request('/printer')
        self.assertEqual(status, 200)
        self.assertEqual(result['vendor_id'], '2aaf')
        self.assertEqual(result['product_id'], '6015')
        self.assertFalse(result['connected'])
        self.assertEqual(self.request('/health')[0], 200)

    def test_health(self):
        self.assertEqual(self.request('/health')[0], 200)

    def test_receives_and_persists_data(self):
        payload = {'data': {'venta': 10, 'total': '25000.00', 'nombre': 'Ron edición'}, 'template': 'ticket_venta'}
        status, result = self.request(payload=payload)
        self.assertEqual(status, 202)
        self.assertEqual(result['status'], 'received')
        job = json.loads((Path(self.directory.name) / (result['id'] + '.json')).read_text())
        self.assertEqual(job['data'], payload['data'])
        self.assertEqual(job['template'], 'ticket_venta')
        self.assertEqual(job['status'], 'received')
        self.assertIn('created_at', job)

    def test_template_is_optional(self):
        self.assertEqual(self.request(payload={'data': {}})[0], 202)

    def test_invalid_json(self):
        for body in [b'{broken', b'{"data":{"number":NaN}}', b'{"data":{"number":1e999}}', b'\xff']:
            self.assertEqual(self.request(raw=body)[0], 400)

    def test_invalid_unicode_is_rejected(self):
        self.assertEqual(self.request(raw=b'{"data":{"text":"\\ud800"}}')[0], 422)

    def test_invalid_contract(self):
        for payload in [[], {}, {'data': []}, {'data': None}, {'data': {}, 'template': ''}, {'data': {}, 'template': 12}, {'data': {}, 'unknown': True}]:
            self.assertEqual(self.request(payload=payload)[0], 422)
        self.assertEqual(list(Path(self.directory.name).glob('*.json')), [])

    def test_content_type_and_size(self):
        self.assertEqual(self.request(raw=b'{}', content_type='text/plain')[0], 415)
        # The server rejects oversized headers before reading the body. Sending
        # that body concurrently can cause a client-side broken pipe instead.
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest('POST', '/print')
        connection.putheader('Content-Type', 'application/json')
        connection.putheader('Content-Length', str(MAX_BODY + 1))
        connection.endheaders()
        self.assertEqual(connection.getresponse().status, 413)

    def test_unknown_route(self):
        self.assertEqual(self.request('/unknown')[0], 404)

    def test_parallel_requests_get_unique_complete_jobs(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda index: self.request(payload={'data': {'index': index}}), range(10)))
        self.assertTrue(all(status == 202 for status, _ in results))
        ids = {job['id'] for _, job in results}
        self.assertEqual(len(ids), 10)
        jobs = [json.loads(path.read_text()) for path in Path(self.directory.name).glob('*.json')]
        self.assertEqual({job['data']['index'] for job in jobs}, set(range(10)))


class UsbPrinterTest(unittest.TestCase):
    def test_no_printer_does_not_send(self):
        with patch('printer.usb.core.find', return_value=None) as find:
            with self.assertRaises(PrinterUnavailable):
                SatPrinter().test_print()
        find.assert_called_once_with(idVendor=0x2aaf, idProduct=0x6015)

    def test_usb_access_error_is_reported(self):
        with patch('printer.usb.core.find', side_effect=usb.core.USBError('denied')):
            status = SatPrinter().status()
        self.assertFalse(status['connected'])
        self.assertIn('error', status)

    def test_write_and_cleanup_after_success_or_partial_transfer(self):
        for partial in (False, True):
            with self.subTest(partial=partial):
                device = MagicMock()
                interface = MagicMock(bInterfaceClass=7, bInterfaceNumber=0)
                endpoint = MagicMock(bEndpointAddress=1)
                device.get_active_configuration.return_value = [interface]
                device.is_kernel_driver_active.return_value = True
                device.write.return_value = 1 if partial else 3
                with patch('printer.usb.core.find', return_value=device), \
                     patch('printer.usb.util.find_descriptor', return_value=endpoint), \
                     patch('printer.usb.util.claim_interface') as claim, \
                     patch('printer.usb.util.release_interface') as release, \
                     patch('printer.usb.util.dispose_resources') as dispose:
                    if partial:
                        with self.assertRaises(PrinterUnavailable):
                            SatPrinter().write(b'abc')
                    else:
                        SatPrinter().write(b'abc')
                device.write.assert_called_once_with(1, b'abc', timeout=5000)
                claim.assert_called_once_with(device, 0)
                release.assert_called_once_with(device, 0)
                device.attach_kernel_driver.assert_called_once_with(0)
                dispose.assert_called_once_with(device)


if __name__ == '__main__':
    unittest.main(verbosity=2)
