<?php

namespace App\Authorization;

use App\Entity\User;
use Doctrine\ORM\EntityManagerInterface;

/** Application permissions live in groups, independently of Symfony role voters. */
class PermissionChecker
{
    public function __construct(private readonly EntityManagerInterface $entityManager)
    {
    }

    public function isAdmin(User $user): bool
    {
        return in_array(User::ROLE_ADMIN, $user->getRoles(), true);
    }

    /** @return array<string, array<string, bool>> */
    public function permissionsFor(User $user): array
    {
        $admin = $this->isAdmin($user);
        $granted = [];
        if (!$admin) {
            // Query membership and grants on every request; session data is not authoritative.
            $rows = $this->entityManager->createQuery(
                'SELECT p.module, p.action FROM App\\Entity\\User u JOIN u.group g JOIN g.permissions p WHERE u.id = :id'
            )->setParameter('id', $user->getId())->getArrayResult();
            foreach ($rows as $row) $granted[$row['module']][$row['action']] = true;
        }
        $result = [];
        foreach (Module::cases() as $module) {
            $canView = $admin || isset($granted[$module->value][Action::View->value]);
            foreach (Action::cases() as $action) {
                $result[$module->value][$action->value] = $admin || ($canView && isset($granted[$module->value][$action->value]));
            }
        }

        return $result;
    }

    public function allows(User $user, Module $module, Action $action): bool
    {
        return $this->permissionsFor($user)[$module->value][$action->value];
    }
}
