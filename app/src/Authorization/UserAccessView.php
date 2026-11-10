<?php

namespace App\Authorization;

use App\Entity\User;

class UserAccessView
{
    public function __construct(private readonly PermissionChecker $permissions)
    {
    }

    public function serialize(User $user): array
    {
        $group = $this->permissions->isAdmin($user) ? null : $user->getGroup();

        return [
            'id' => $user->getId(),
            'username' => $user->getUserIdentifier(),
            'roles' => $user->getRoles(),
            'group' => $group ? ['id' => $group->getId(), 'name' => $group->getName()] : null,
            'permissions' => $this->permissions->permissionsFor($user),
        ];
    }
}
