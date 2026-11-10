<?php

namespace App\Authorization;

enum Module: string
{
    case Products = 'products';
    case Sales = 'sales';
    case Inventory = 'inventory';
    case Groups = 'groups';
    case Users = 'users';
    case Permissions = 'permissions';

    public function label(): string
    {
        return match ($this) {
            self::Products => 'Productos', self::Sales => 'Ventas', self::Inventory => 'Inventario',
            self::Groups => 'Grupos', self::Users => 'Usuarios', self::Permissions => 'Permisos',
        };
    }
}
