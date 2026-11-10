# RG La Licorería

Symfony 7.4 skeleton con PHP 8.4 FPM, Nginx, MySQL 8.4, MinIO, Mercure y Redis con un worker de Symfony Messenger.

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
`./volumes/mysql`, `./volumes/minio`, `./volumes/redis`, `./volumes/mercure/data` y
`./volumes/mercure/config`. Se excluyen de Git y conservan los datos
al detener los servicios.

| Servicio | Dirección desde el host | Dirección desde PHP |
| --- | --- | --- |
| Symfony / Nginx | http://localhost | — |
| Redis | sin puerto publicado | redis:6379 |
| MySQL | 127.0.0.1:3306 | mysql:3306 |
| MinIO S3 | http://localhost:9000 | http://minio:9000 |
| MinIO consola | http://localhost:9001 | — |
| Mercure | http://localhost/.well-known/mercure | http://mercure/.well-known/mercure |

Para acceder desde otra máquina, ajustar las URLs de `app/.env.local`.
Las suscripciones a Mercure requieren un JWT válido; el proxy desactiva el
buffering para permitir eventos SSE.

Se parte del skeleton y se agrega Messenger con el transporte Redis para el
worker. No incluye Doctrine, SDK S3 ni el bundle Mercure. Las variables de conexión quedan preparadas para integrarlos después.
El bucket indicado por `MINIO_BUCKET` todavía no se crea automáticamente.
Sin rutas propias, Symfony muestra su respuesta inicial del skeleton (HTTP 404).

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
