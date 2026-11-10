<?php

namespace App\Controller;

use App\Authorization\UserAccessView;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\Security\Csrf\CsrfTokenManagerInterface;
use Symfony\Component\Security\Http\Attribute\IsGranted;

#[Route('/api', defaults: ['_format' => 'json'])]
class ApiSecurityController extends AbstractController
{
    #[Route('/csrf', name: 'api_csrf', methods: ['GET'])]
    public function csrf(CsrfTokenManagerInterface $csrf): JsonResponse
    {
        return $this->json([
            'login' => $csrf->getToken('authenticate')->getValue(),
            'logout' => $csrf->getToken('logout')->getValue(),
            'products' => $csrf->getToken('products')->getValue(),
            'sales' => $csrf->getToken('sales')->getValue(),
            'groups' => $csrf->getToken('groups')->getValue(),
            'permissions' => $csrf->getToken('permissions')->getValue(),
            'users' => $csrf->getToken('users')->getValue(),
        ], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/login', name: 'api_login', methods: ['POST'])]
    public function login(): never
    {
        throw new \LogicException('El autenticador gestiona el acceso.');
    }

    #[Route('/logout', name: 'api_logout', methods: ['POST'])]
    public function logout(): never
    {
        throw new \LogicException('El firewall gestiona el cierre de sesión.');
    }

    #[Route('/me', name: 'api_me', methods: ['GET'])]
    public function me(UserAccessView $users): JsonResponse
    {
        $user = $this->getUser();

        return $this->json(['user' => $users->serialize($user)], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/admin', name: 'api_admin', methods: ['GET'])]
    #[IsGranted('ROLE_ADMIN')]
    public function admin(): JsonResponse
    {
        return $this->json(['message' => 'Tienes acceso al panel de administración.'], headers: ['Cache-Control' => 'no-store']);
    }
}
