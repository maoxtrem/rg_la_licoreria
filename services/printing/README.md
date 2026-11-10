# Receptor de impresión

## Apertura de caja al imprimir facturas

Los trabajos con `template: "invoice"` imprimen la factura pagada, cortan el
papel y envían la orden de apertura de caja, en ese orden y en el mismo envío
USB. La caja debe estar conectada al puerto de cajón de la impresora.
Se usa [ESC p](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/esc_lp.html)
con pin 2, pulso de 100 ms y reposo de 500 ms. La deduplicación del trabajo
evita volver a imprimir o enviar el pulso si se recibe de nuevo el mismo trabajo.
Los envíos inciertos no se repiten automáticamente. El estado `sent` confirma
el envío USB, no la impresión ni la apertura física. El ticket de prueba
`printer.py --test` solo imprime y corta.

Servicio interno e independiente del monolito, implementado con Python 3.12. El transporte USB usa PyUSB y libusb. Recibe solicitudes y conserva su JSON; todavía no
renderiza plantillas ni envía datos a una impresora.

## Contrato

`POST http://printing:8080/print`, con `Content-Type: application/json`:

```json
{
  "template": "ticket_venta",
  "data": {
    "numero": "V-001",
    "productos": [{"nombre": "Ron 750 ml", "cantidad": 2}],
    "total": "90000.00"
  }
}
```

Solo `data` es obligatorio y debe ser un objeto. Su contenido queda libre para
las futuras plantillas. `template` es opcional: por ahora solo se guarda su nombre,
sin validar la existencia ni ejecutar una plantilla. Usar cadenas para importes
que deban conservar sus decimales exactos. Tamaño máximo: 1 MiB.

Respuesta `202 Accepted` después de guardar la solicitud:

```json
{"id":"UUID de la solicitud","status":"received"}
```

`received` significa **recibido y guardado**, no impreso ni procesado. Cada trabajo
se guarda como `/data/{id}.json`, incluyendo `data`, `template`, `status` y
`created_at` en UTC. El directorio corresponde a `./volumes/printing` en el host.
Los archivos se publican de forma atómica antes de confirmar la recepción.

Errores: JSON inválido 400, longitud ausente 411, cuerpo demasiado grande 413,
tipo de contenido incorrecto 415, contrato inválido 422 y almacenamiento no
disponible 503. El cuerpo de la solicitud no se registra en los logs.

`GET /health` devuelve 200 cuando el receptor tiene acceso al directorio de datos.

## Docker

Desde la raíz del repositorio:

```bash
docker compose --env-file app/.env.local up -d --build --wait printing
docker compose --env-file app/.env.local logs -f printing
```

El servicio usa `restart: always` y no publica puertos al host. Los contenedores
del Compose lo llaman mediante `http://printing:8080`. El monolito tiene esa URL
en `PRINT_SERVICE_URL`, dentro de `app/.env.local`.
El consumidor previsto es el worker de Messenger mediante la cola `async`.
Compose espera a que el receptor esté saludable antes de arrancar el worker;
el manejador que enviará las solicitudes de impresión aún no está implementado.

Todavía no hay una ruta pública ni conexión automática desde Ventas. Cuando se
integre, el backend deberá comprobar el permiso correspondiente antes de enviar
la solicitud. El navegador no llama directamente al receptor.

Pruebas HTTP con almacenamiento temporal independiente:

```bash
docker compose --env-file app/.env.local run --rm --no-deps printing python -m unittest -v tests
```

Las futuras etapas serán definir las plantillas, el formato de salida y el
transporte hacia la impresora, conservando este contrato de recepción.

## Impresora SAT Q23T UE por USB

Perfil configurado: VID `2aaf`, PID `6015`, protocolo ESC/POS. La variante UE
incluye USB y Ethernet según la [ficha de SAT](https://satpcs.com/Descargas/Fichas-tecnicas/impresora-termica-sat-q23t.pdf).
Los identificadores se pueden cambiar mediante `PRINT_USB_VENDOR_ID` y
`PRINT_USB_PRODUCT_ID` (hexadecimal). No se fija el puerto físico `1-1`/`1-2`,
porque puede cambiar al reconectar.

En Windows/WSL, consultar `usbipd list`. Compartir el BUSID actual en
PowerShell **como administrador** (solo la primera vez):

```powershell
usbipd bind --busid 1-1
```

Después adjuntarla a WSL desde PowerShell normal:

```powershell
usbipd attach --wsl --busid 1-1
```

Comprobar `lsusb -d 2aaf:6015` en Linux. Con la impresora conectada, activar el
acceso USB del contenedor usando ambos archivos Compose:

```bash
docker compose --env-file app/.env.local -f docker-compose.yml -f docker-compose.printing-usb.yml up -d --build --wait printing
```

El archivo adicional monta `/dev/bus/usb` y permite dispositivos USB (major 189)
para tolerar cambios de dirección al reconectar. No requiere `privileged`.
El montaje requiere que `/dev/bus/usb` exista en el host del daemon Docker.
Después de reiniciar WSL o desconectar el USB, puede ser necesario repetir
`usbipd attach`. Mientras se use USB, mantener los dos archivos `-f` al ejecutar
`up` para no quitar la configuración del contenedor.

Consultar el dispositivo dentro del servicio:

```bash
docker compose --env-file app/.env.local exec printing python printer.py
```

`GET /printer` devuelve el modelo, los identificadores y `connected`.
Este estado indica presencia USB, no disponibilidad de papel ni confirmación
física de impresión. `/health` sigue comprobando el receptor de trabajos,
independientemente de si la impresora está conectada.

Para imprimir un ticket físico de prueba con corte:

```bash
docker compose --env-file app/.env.local exec printing python printer.py --test
```

El transporte descubre la interfaz de impresión y su endpoint bulk OUT. Los
fallos o envíos parciales no se reintentan automáticamente para evitar tickets
duplicados. `POST /print` conserva su contrato: guarda el JSON con estado
`received`; la conexión entre esos trabajos, las plantillas y el transporte
USB sigue pendiente. El ticket de prueba es una operación explícita separada.
