<?php

namespace App\Controller;

use App\Authorization\GroupPermissionEditor;
use App\Authorization\GroupView;
use App\Authorization\Module;
use App\Entity\Permission;
use App\Entity\UserGroup;
use App\Http\ApiInput;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\Security\Http\Attribute\IsGranted;

#[Route('/api', defaults: ['_format' => 'json', '_permission_module' => 'permissions'])]
class ApiPermissionController extends AbstractController
{
    #[Route('/permissions', name: 'api_permissions_list', methods: ['GET'])]
    public function index(EntityManagerInterface $entityManager): JsonResponse
    {
        $permissions = $entityManager->getRepository(Permission::class)->findBy([], ['module' => 'ASC', 'action' => 'ASC']);
        $data = array_map(static fn (Permission $permission) => [
            'key' => $permission->getKey(), 'module' => $permission->getModule(),
            'action' => $permission->getAction(), 'module_label' => Module::from($permission->getModule())->label(),
        ], $permissions);

        return $this->json(['data' => $data], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/groups/{id}/permissions', name: 'api_groups_permissions', requirements: ['id' => '\d+'], methods: ['PUT'])]
    #[IsGranted('ROLE_ADMIN')]
    public function replace(int $id, Request $request, ApiInput $input, EntityManagerInterface $entityManager, GroupPermissionEditor $editor, GroupView $view): JsonResponse
    {
        $data = $input->read($request, 'permissions');
        if (array_keys($data) !== ['permissions']) return $this->json(['error' => 'Incluye únicamente la lista permissions.'], 422);
        $result = $editor->resolve($data['permissions']);
        if ($result['error']) return $this->json(['error' => $result['error']], 422);
        $group = $entityManager->find(UserGroup::class, $id) ?? throw $this->createNotFoundException();
        $group->replacePermissions($result['permissions']);
        $entityManager->flush();

        return $this->json(['data' => $view->serialize($group)]);
    }
}
