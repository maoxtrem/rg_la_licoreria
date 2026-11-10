<?php

namespace App\Controller;

use App\Authorization\PermissionChecker;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;

class ApiModuleController extends AbstractController
{
    #[Route('/api/modules/{_permission_module}/access', name: 'api_module_access', defaults: ['_format' => 'json'], requirements: ['_permission_module' => 'products|sales|inventory|groups|users|permissions'], methods: ['GET'])]
    public function access(string $_permission_module, PermissionChecker $permissions): JsonResponse
    {
        return $this->json(['module' => $_permission_module, 'actions' => $permissions->permissionsFor($this->getUser())[$_permission_module]], headers: ['Cache-Control' => 'no-store']);
    }
}
