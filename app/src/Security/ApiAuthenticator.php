<?php

namespace App\Security;

use App\Authorization\UserAccessView;
use App\Http\AccessDeniedResponder;

use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Exception\JsonException;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Security\Core\Authentication\Token\TokenInterface;
use Symfony\Component\Security\Core\Exception\AccessDeniedException;
use Symfony\Component\Security\Core\Exception\AuthenticationException;
use Symfony\Component\Security\Core\Exception\CustomUserMessageAuthenticationException;
use Symfony\Component\Security\Http\Authenticator\AbstractAuthenticator;
use Symfony\Component\Security\Http\Authenticator\Passport\Badge\CsrfTokenBadge;
use Symfony\Component\Security\Http\Authenticator\Passport\Badge\UserBadge;
use Symfony\Component\Security\Http\Authenticator\Passport\Credentials\PasswordCredentials;
use Symfony\Component\Security\Http\Authenticator\Passport\Passport;
use Symfony\Component\Security\Http\Authorization\AccessDeniedHandlerInterface;
use Symfony\Component\Security\Http\EntryPoint\AuthenticationEntryPointInterface;

class ApiAuthenticator extends AbstractAuthenticator implements AuthenticationEntryPointInterface, AccessDeniedHandlerInterface
{
    public function __construct(private readonly UserAccessView $users, private readonly AccessDeniedResponder $denied)
    {
    }

    public function supports(Request $request): ?bool
    {
        return $request->attributes->get('_route') === 'api_login' && $request->isMethod('POST');
    }

    public function authenticate(Request $request): Passport
    {
        try {
            $data = $request->toArray();
        } catch (JsonException) {
            throw new CustomUserMessageAuthenticationException('Solicitud de acceso no válida.');
        }

        $username = $data['username'] ?? null;
        $password = $data['password'] ?? null;
        $csrfToken = $data['_csrf_token'] ?? '';

        if (!is_string($username) || trim($username) === '' || strlen($username) > 180
            || !is_string($password) || $password === '' || strlen($password) > 4096
            || !is_string($csrfToken)) {
            throw new CustomUserMessageAuthenticationException('Solicitud de acceso no válida.');
        }

        return new Passport(
            new UserBadge(trim($username)),
            new PasswordCredentials($password),
            [new CsrfTokenBadge('authenticate', $csrfToken)],
        );
    }

    public function onAuthenticationSuccess(Request $request, TokenInterface $token, string $firewallName): ?Response
    {
        $user = $token->getUser();

        return new JsonResponse(['user' => $this->users->serialize($user)], headers: ['Cache-Control' => 'no-store']);
    }

    public function onAuthenticationFailure(Request $request, AuthenticationException $exception): ?Response
    {
        return new JsonResponse(['error' => 'No se pudo iniciar sesión. Revisa tus credenciales y vuelve a intentarlo.'], Response::HTTP_UNAUTHORIZED);
    }

    public function start(Request $request, ?AuthenticationException $authException = null): Response
    {
        return new JsonResponse(['error' => 'Debes iniciar sesión.'], Response::HTTP_UNAUTHORIZED);
    }

    public function handle(Request $request, AccessDeniedException $accessDeniedException): ?Response
    {
        return $this->denied->respond($request);
    }
}
