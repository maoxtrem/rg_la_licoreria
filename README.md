# RG La Licorería

Symfony 7.4 skeleton con PHP 8.4 FPM, Nginx, MySQL 8.4, MinIO, Mercure, Redis con un worker de Symfony Messenger y un receptor de impresión.

## Configuración local

Las variables y credenciales están en `app/.env.local`, excluido de Git.
Compose debe recibir ese archivo explícitamente. Symfony lo carga automáticamente.
`LOCAL_UID` y `LOCAL_GID` corresponden al usuario del host para evitar archivos
creados como root en `app`.

```bash
docker compose --env-file app/.env.local up -d --build --wait
docker compose --env-file app/.env.local ps
docker compose --env-file app/.env.local down
```

Todos los servicios usan `restart: always`. Docker está habilitado para iniciar
con el servidor, por lo que los contenedores existentes volverán a arrancar al
encenderlo. `docker compose down` elimina los contenedores: después de ese comando
es necesario ejecutar `up -d` para crearlos nuevamente.

Los datos se guardan en carpetas del host relativas al Compose:
`./volumes/mysql`, `./volumes/minio`, `./volumes/redis`, `./volumes/printing`, `./volumes/mercure/data` y
`./volumes/mercure/config`. Se excluyen de Git y conservan los datos
al detener los servicios.

| Servicio | Dirección desde el host | Dirección desde PHP |
| --- | --- | --- |
| Symfony / Nginx | http://localhost | — |
| Impresión | sin puerto publicado | http://printing:8080 |
| Redis | sin puerto publicado | redis:6379 |
| MySQL | 127.0.0.1:3306 | mysql:3306 |
| MinIO S3 | http://localhost:9000 | http://minio:9000 |
| MinIO consola | http://localhost:9001 | — |
| Mercure | http://localhost/.well-known/mercure | http://mercure/.well-known/mercure |

Para acceder desde otra máquina, ajustar las URLs de `app/.env.local`.
Las suscripciones a Mercure requieren un JWT válido; el proxy desactiva el
buffering para permitir eventos SSE.

El monolito incluye autenticación y permisos por grupo, Productos y el carrito de
Ventas. Los detalles de la API están en [app/README.md](app/README.md).
El bucket indicado por `MINIO_BUCKET` todavía no se crea automáticamente.

El servicio `printing` recibe JSON en `POST /print`, lo guarda en
`./volumes/printing` y responde `202` con estado `received`. Todavía no renderiza
plantillas ni imprime esos trabajos. Incluye el perfil USB `2aaf:6015` de la
SAT Q23T UE, consulta en `GET /printer` y un comando de impresión de prueba.
El acceso USB se activa con `docker-compose.printing-usb.yml` después de
compartir la impresora con Linux/WSL. Su URL interna se configura con `PRINT_SERVICE_URL` en
`app/.env.local`. Contrato y comandos en
[services/printing/README.md](services/printing/README.md).
El worker será quien envíe las solicitudes a ese servicio desde la cola `async`;
su arranque espera a que `printing` esté saludable. El manejador de mensajes de
impresión todavía está pendiente de implementar.

MinIO se compila desde el código oficial de la versión
`RELEASE.2025-10-15T17-29-55Z`, porque las imágenes oficiales ya no se pudieron
descargar. La primera construcción requiere descargar Go y sus dependencias.

El worker consume `async`. Los mensajes bajo `App\Message\` se envían a Redis;
tras tres reintentos, los fallidos pasan al transporte `failed`. Redis usa AOF
para persistencia. Se incluye PCNTL para detener el worker mediante señales.
El consumidor `worker-1` corresponde a una sola instancia del worker.

## Comandos de Symfony y Composer

```bash
docker compose --env-file app/.env.local exec php php bin/console about
docker compose --env-file app/.env.local exec php composer install
```

Después de clonar, instalar las dependencias antes de iniciar el entorno:

```bash
docker compose --env-file app/.env.local build php
docker compose --env-file app/.env.local run --rm --no-deps php composer install
docker compose --env-file app/.env.local up -d --build --wait
```

Crear previamente `app/.env.local` a partir de `app/.env.local.example`,
reemplazar los valores `CHANGE_ME` y ajustar `LOCAL_UID` / `LOCAL_GID`
con `id -u` / `id -g`. Mantener la misma contraseña en `MYSQL_PASSWORD`
y `DATABASE_URL`.
Las contraseñas de MySQL se aplican al inicializar un volumen vacío; cambiarlas
en el archivo no actualiza usuarios de una base de datos ya inicializada.
