<?php

namespace App\Authorization;

enum Action: string
{
    case View = 'view';
    case Create = 'create';
    case Update = 'update';
    case Delete = 'delete';

    public static function forMethod(string $method): ?self
    {
        return match ($method) {
            'GET', 'HEAD' => self::View,
            'POST' => self::Create,
            'PUT', 'PATCH' => self::Update,
            'DELETE' => self::Delete,
            default => null,
        };
    }
}
