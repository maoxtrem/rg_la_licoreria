<?php

namespace App\Controller;

use App\Authorization\PermissionChecker;
use App\Entity\User;
use App\Entity\UserGroup;
use App\Http\ApiInput;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\Security\Http\Attribute\IsGranted;

#[Route('/api/users', defaults: ['_format' => 'json', '_permission_module' => 'users'])]
class ApiUserGroupController extends AbstractController
{
    #[Route('', name: 'api_users_list', methods: ['GET'])]
    public function index(Request $request, ApiInput $input, EntityManagerInterface $entityManager): JsonResponse
    {
        $page = $input->pagination($request);
        $repository = $entityManager->getRepository(User::class);
        $users = $repository->findBy([], ['username' => 'ASC'], $page['limit'], $page['offset']);
        $data = array_map(static function (User $user) {
            $group = $user->getGroup();
            return ['id' => $user->getId(), 'username' => $user->getUsername(), 'roles' => $user->getRoles(),
                'group' => $group ? ['id' => $group->getId(), 'name' => $group->getName()] : null];
        }, $users);

        return $this->json(['data' => $data, 'pagination' => ['page' => $page['page'], 'limit' => $page['limit'], 'total' => $repository->count([])]], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}/group', name: 'api_users_assign_group', requirements: ['id' => '\d+'], methods: ['PUT'])]
    #[IsGranted('ROLE_ADMIN')]
    public function assign(int $id, Request $request, ApiInput $input, EntityManagerInterface $entityManager, PermissionChecker $permissions): JsonResponse
    {
        $data = $input->read($request, 'users');
        if (array_keys($data) !== ['group_id'] || ($data['group_id'] !== null && (!is_int($data['group_id']) || $data['group_id'] < 1))) {
            return $this->json(['error' => 'Incluye únicamente group_id, un entero positivo o null.'], 422);
        }
        $user = $entityManager->find(User::class, $id) ?? throw $this->createNotFoundException();
        if ($permissions->isAdmin($user)) return $this->json(['error' => 'Los administradores no dependen de grupos.'], 422);
        $group = $data['group_id'] === null ? null : ($entityManager->find(UserGroup::class, $data['group_id']) ?? throw $this->createNotFoundException());
        $user->setGroup($group);
        $entityManager->flush();

        return $this->json(['data' => ['id' => $user->getId(), 'username' => $user->getUsername(),
            'group' => $group ? ['id' => $group->getId(), 'name' => $group->getName()] : null]]);
    }
}
