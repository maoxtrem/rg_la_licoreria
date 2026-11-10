<?php

namespace App\Authorization;

use App\Entity\Permission;
use Doctrine\ORM\EntityManagerInterface;

class GroupPermissionEditor
{
    public function __construct(private readonly EntityManagerInterface $entityManager)
    {
    }

    /** @return array{permissions: list<Permission>, error: ?string} */
    public function resolve(mixed $keys): array
    {
        if (!is_array($keys) || !array_is_list($keys) || count($keys) > count(Module::cases()) * count(Action::cases())) {
            return ['permissions' => [], 'error' => 'Incluye una lista de claves de permisos del catálogo.'];
        }
        $catalog = [];
        foreach ($this->entityManager->getRepository(Permission::class)->findAll() as $permission) {
            $catalog[$permission->getKey()] = $permission;
        }
        $permissions = [];
        foreach ($keys as $key) {
            if (!is_string($key) || !isset($catalog[$key])) {
                return ['permissions' => [], 'error' => 'Uno o más permisos no existen en el catálogo.'];
            }
            $permissions[$key] = $catalog[$key];
        }
        foreach ($permissions as $permission) {
            if ($permission->getAction() !== Action::View->value && !isset($permissions[$permission->getModule().'.view'])) {
                return ['permissions' => [], 'error' => 'Para asignar acciones de un módulo debes incluir su permiso de ver.'];
            }
        }

        return ['permissions' => array_values($permissions), 'error' => null];
    }
}
