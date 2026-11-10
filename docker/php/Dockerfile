FROM php:8.4-fpm-alpine

RUN apk add --no-cache icu-libs libzip \
    && apk add --no-cache --virtual .build-deps $PHPIZE_DEPS icu-dev libzip-dev \
    && docker-php-ext-install intl pdo_mysql zip opcache \
    && apk del .build-deps

RUN apk add --no-cache --virtual .redis-build-deps $PHPIZE_DEPS \
    && docker-php-ext-install -j2 pcntl \
    && pecl install redis-6.3.0 \
    && docker-php-ext-enable redis \
    && apk del --no-network .redis-build-deps

COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer
WORKDIR /var/www/app
