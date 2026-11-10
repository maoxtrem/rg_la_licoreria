<?php

namespace App\Http;

use Symfony\Component\HttpFoundation\Exception\JsonException;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\Exception\BadRequestHttpException;
use Symfony\Component\Security\Csrf\CsrfToken;
use Symfony\Component\Security\Csrf\CsrfTokenManagerInterface;

class ApiInput
{
    public function __construct(private readonly CsrfTokenManagerInterface $csrf)
    {
    }

    /** @return array{page: int, limit: int, offset: int} */
    public function pagination(Request $request): array
    {
        $page = filter_var($request->query->get('page', '1'), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $limit = filter_var($request->query->get('limit', '20'), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 100]]);
        if ($page === false || $limit === false || $page > intdiv(PHP_INT_MAX, $limit)) throw new BadRequestHttpException();

        return ['page' => $page, 'limit' => $limit, 'offset' => ($page - 1) * $limit];
    }

    public function read(Request $request, string $csrfId): array
    {
        $token = $request->headers->get('X-CSRF-Token', '');
        if (!$this->csrf->isTokenValid(new CsrfToken($csrfId, $token))) throw new AccessDeniedHttpException();
        try {
            $data = $request->toArray();
        } catch (JsonException $exception) {
            throw new BadRequestHttpException(previous: $exception);
        }
        if (!str_starts_with(ltrim($request->getContent()), '{')) throw new BadRequestHttpException();

        return $data;
    }

    public function checkCsrf(Request $request, string $csrfId): void
    {
        if (!$this->csrf->isTokenValid(new CsrfToken($csrfId, $request->headers->get('X-CSRF-Token', '')))) {
            throw new AccessDeniedHttpException();
        }
    }
}
