<?php

namespace App\Http;

use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Twig\Environment;

class AccessDeniedResponder
{
    public function __construct(private readonly Environment $twig)
    {
    }

    public function respond(Request $request): Response
    {
        $accept = $request->headers->get('Accept', '');
        $headers = ['Cache-Control' => 'no-store', 'Vary' => 'Accept'];
        if (str_contains($accept, 'text/html') && !str_contains($accept, 'application/json')) {
            return new Response($this->twig->render('app/access-denied.html.twig'), Response::HTTP_FORBIDDEN, $headers);
        }

        return new JsonResponse(['error' => 'No tienes permiso para realizar esta acción.'], Response::HTTP_FORBIDDEN, $headers);
    }
}
