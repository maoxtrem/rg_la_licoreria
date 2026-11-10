<?php

namespace App\EventListener;

use App\Http\AccessDeniedResponder;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpKernel\Event\ExceptionEvent;
use Symfony\Component\HttpKernel\Exception\HttpExceptionInterface;
use Symfony\Component\HttpKernel\KernelEvents;

#[AsEventListener(event: KernelEvents::EXCEPTION, priority: -64)]
class ApiExceptionListener
{
    public function __construct(private readonly AccessDeniedResponder $denied)
    {
    }

    public function __invoke(ExceptionEvent $event): void
    {
        $exception = $event->getThrowable();
        $status = $exception instanceof HttpExceptionInterface ? $exception->getStatusCode() : 500;
        if ($status === 403) {
            $event->setResponse($this->denied->respond($event->getRequest()));
            return;
        }
        if (!str_starts_with($event->getRequest()->getPathInfo(), '/api/')) return;
        $message = match ($status) {
            400 => 'Solicitud no válida.',
            401 => 'Debes iniciar sesión.',
            403 => 'Solicitud no autorizada. Actualiza la página e inténtalo nuevamente.',
            404 => 'Recurso no encontrado.',
            405 => 'Método no permitido.',
            default => 'No se pudo completar la solicitud.',
        };
        if ($exception instanceof \App\Sales\CartException) {
            $message = $exception->getMessage();
        }
        $headers = $exception instanceof HttpExceptionInterface ? $exception->getHeaders() : [];
        $headers['Cache-Control'] = 'no-store';
        $event->setResponse(new JsonResponse(['error' => $message], $status, $headers));
    }
}
