<?php

namespace App\Controller;

use App\Authorization\GroupView;
use App\Entity\User;
use App\Entity\UserGroup;
use App\Http\ApiInput;
use Doctrine\DBAL\Exception\ForeignKeyConstraintViolationException;
use Doctrine\DBAL\Exception\UniqueConstraintViolationException;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

#[Route('/api/groups', defaults: ['_format' => 'json', '_permission_module' => 'groups'])]
class ApiGroupController extends AbstractController
{
    public function __construct(
        private readonly EntityManagerInterface $entityManager,
        private readonly ApiInput $input,
        private readonly GroupView $view,
    ) {
    }

    #[Route('', name: 'api_groups_list', methods: ['GET'])]
    public function index(Request $request): JsonResponse
    {
        $page = $this->input->pagination($request);
        $repository = $this->entityManager->getRepository(UserGroup::class);
        $groups = $repository->findBy([], ['name' => 'ASC'], $page['limit'], $page['offset']);

        return $this->json(['data' => array_map($this->view->serialize(...), $groups),
            'pagination' => ['page' => $page['page'], 'limit' => $page['limit'], 'total' => $repository->count([])]], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}', name: 'api_groups_show', requirements: ['id' => '\d+'], methods: ['GET'])]
    public function show(int $id): JsonResponse
    {
        return $this->json(['data' => $this->view->serialize($this->find($id))], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('', name: 'api_groups_create', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'groups');
        if (!$this->validName($data)) return $this->invalidName();
        $group = new UserGroup(trim($data['name']));
        $this->entityManager->persist($group);

        return $this->save($group, Response::HTTP_CREATED);
    }

    #[Route('/{id}', name: 'api_groups_update', requirements: ['id' => '\d+'], methods: ['PUT', 'PATCH'])]
    public function update(int $id, Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'groups');
        if (!$this->validName($data)) return $this->invalidName();
        $group = $this->find($id);
        $group->setName(trim($data['name']));

        return $this->save($group);
    }

    #[Route('/{id}', name: 'api_groups_delete', requirements: ['id' => '\d+'], methods: ['DELETE'])]
    public function delete(int $id, Request $request): Response
    {
        $this->input->checkCsrf($request, 'groups');
        $group = $this->find($id);
        if ($this->entityManager->getRepository(User::class)->count(['group' => $group]) > 0) {
            return $this->json(['error' => 'Reasigna o retira los usuarios antes de eliminar el grupo.'], 409);
        }
        $this->entityManager->remove($group);
        try {
            $this->entityManager->flush();
        } catch (ForeignKeyConstraintViolationException) {
            return $this->json(['error' => 'El grupo tiene usuarios asignados.'], 409);
        }

        return new Response(status: Response::HTTP_NO_CONTENT);
    }

    private function validName(array $data): bool
    {
        return array_keys($data) === ['name'] && is_string($data['name']) && trim($data['name']) !== '' && mb_strlen(trim($data['name'])) <= 100;
    }

    private function invalidName(): JsonResponse
    {
        return $this->json(['error' => 'Incluye únicamente name, un texto de entre 1 y 100 caracteres.'], 422);
    }

    private function save(UserGroup $group, int $status = 200): JsonResponse
    {
        try {
            $this->entityManager->flush();
        } catch (UniqueConstraintViolationException) {
            return $this->json(['error' => 'Ya existe un grupo con ese nombre.'], 409);
        }

        return $this->json(['data' => $this->view->serialize($group)], $status);
    }

    private function find(int $id): UserGroup
    {
        return $this->entityManager->find(UserGroup::class, $id) ?? throw $this->createNotFoundException();
    }
}
