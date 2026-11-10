<?php

namespace App\Authorization;

use App\Entity\UserGroup;

class GroupView
{
    public function serialize(UserGroup $group): array
    {
        $keys = $group->getPermissions()->map(static fn ($permission) => $permission->getKey())->toArray();
        sort($keys);

        return ['id' => $group->getId(), 'name' => $group->getName(), 'permissions' => $keys];
    }
}
