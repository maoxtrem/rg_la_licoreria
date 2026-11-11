"""SAT Q23T UE USB transport; independent from the JSON reception spool."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import usb.core
import usb.util


class PrinterUnavailable(Exception):
    pass


class UsbPrinter:
    def __init__(self):
        self.vendor_id = int(os.environ.get('PRINT_USB_VENDOR_ID', '2aaf'), 16)
        self.product_id = int(os.environ.get('PRINT_USB_PRODUCT_ID', '6015'), 16)
        self.lock = threading.Lock()

    def _find(self):
        return usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)

    def status(self):
        result = {'model': 'SAT Q23T UE', 'transport': 'usb', 'protocol': 'ESC/POS',
                  'vendor_id': f'{self.vendor_id:04x}', 'product_id': f'{self.product_id:04x}'}
        try:
            with self.lock:
                device = self._find()
                result['connected'] = device is not None
                if device is not None:
                    try:
                        result.update(bus=device.bus, address=device.address)
                    finally:
                        usb.util.dispose_resources(device)
        except (usb.core.USBError, usb.core.NoBackendError):
            result.update(connected=False, error='No se pudo consultar el dispositivo USB.')
        return result

    def write(self, payload):
        """Send once; a partial/failed write must never be retried automatically."""
        with self.lock:
            device = None
            interface = None
            detached = False
            claimed = False
            try:
                device = self._find()
                if device is None:
                    raise PrinterUnavailable('SAT Q23T UE no está conectada al servicio.')
                configuration = device.get_active_configuration()
                for candidate in configuration:
                    if candidate.bInterfaceClass != 7:  # USB printer class
                        continue
                    endpoint = usb.util.find_descriptor(
                        candidate,
                        custom_match=lambda ep: usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT
                        and usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK)
                    if endpoint is not None:
                        interface = candidate.bInterfaceNumber
                        break
                else:
                    raise PrinterUnavailable('No se encontró una interfaz USB de impresión bulk OUT.')
                if device.is_kernel_driver_active(interface):
                    device.detach_kernel_driver(interface)
                    detached = True
                usb.util.claim_interface(device, interface)
                claimed = True
                written = device.write(endpoint.bEndpointAddress, payload, timeout=5000)
                if written != len(payload):
                    raise PrinterUnavailable('Envío incompleto; verifica el papel antes de repetir.')
            except (usb.core.USBError, usb.core.NoBackendError) as error:
                raise PrinterUnavailable('Falló el envío USB; verifica la impresora antes de repetir.') from error
            finally:
                if device is not None:
                    try:
                        if claimed:
                            usb.util.release_interface(device, interface)
                    finally:
                        try:
                            if detached:
                                device.attach_kernel_driver(interface)
                        finally:
                            usb.util.dispose_resources(device)

    def test_print(self):
        self.write(b'\x1b@RG LA LICORERIA\nSAT Q23T UE\nPrueba de impresion USB\n2aaf:6015\n\n\n\n\x1dV\x01')


class SatPrinter:
    """Use a fresh libusb context for every operation after USB reconnection.

    Docker does not always deliver hotplug events to a long-lived libusb
    context. A short-lived process enumerates the current devices instead.
    Failed writes are never repeated, since paper may already have printed.
    """
    def __init__(self):
        self.lock = threading.Lock()

    def _run(self, *arguments, payload=None):
        return subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *arguments],
            input=payload, capture_output=True, timeout=15, check=True)

    def status(self):
        with self.lock:
            try:
                return json.loads(self._run().stdout)
            except (OSError, subprocess.SubprocessError, ValueError):
                return {'connected': False, 'error': 'No se pudo consultar el dispositivo USB.'}

    def write(self, payload):
        with self.lock:
            try:
                self._run('--write-stdin', payload=payload)
            except (OSError, subprocess.SubprocessError) as error:
                raise PrinterUnavailable('Falló el envío USB; verifica la impresora antes de repetir.') from error


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SAT Q23T UE USB')
    parser.add_argument('--test', action='store_true', help='Imprime un ticket físico de prueba y corta el papel.')
    parser.add_argument('--write-stdin', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    printer = UsbPrinter()
    if args.test or args.write_stdin:
        try:
            if args.write_stdin:
                printer.write(sys.stdin.buffer.read())
            else:
                printer.test_print()
        except (PrinterUnavailable, usb.core.USBError) as error:
            parser.exit(1, str(error) + '\n')
        print('Ticket enviado por USB; verifica la salida física.')
    else:
        print(json.dumps(printer.status(), ensure_ascii=False))
