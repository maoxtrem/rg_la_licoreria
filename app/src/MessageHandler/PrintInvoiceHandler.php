<?php

namespace App\MessageHandler;

use App\Message\PrintInvoice;
use Symfony\Component\DependencyInjection\Attribute\Autowire;
use Symfony\Component\Messenger\Attribute\AsMessageHandler;
use Symfony\Component\Messenger\Exception\UnrecoverableMessageHandlingException;

#[AsMessageHandler]
final class PrintInvoiceHandler
{
    public function __construct(#[Autowire('%env(PRINT_SERVICE_URL)%')] private readonly string $url) {}

    public function __invoke(PrintInvoice $message): void
    {
        $body = json_encode(['template' => 'invoice', 'data' => ['print_job_id' => $message->jobId, 'invoice' => $message->invoice]], JSON_THROW_ON_ERROR);
        $context = stream_context_create(['http' => ['method' => 'POST', 'header' => "Content-Type: application/json\r\n",
            'content' => $body, 'timeout' => 20, 'ignore_errors' => true]]);
        $response = @file_get_contents(rtrim($this->url, '/').'/print', false, $context);
        $status = isset($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $match) ? (int) $match[1] : 0;
        if (in_array($status, [400, 409, 415, 422], true)) {
            throw new UnrecoverableMessageHandlingException('Impresión rechazada o de resultado incierto; revisar antes de reenviar.');
        }
        $result = $response !== false ? json_decode($response, true) : null;
        if ($status !== 200 || ($result['status'] ?? null) !== 'sent') {
            throw new \RuntimeException('El microservicio no confirmó el envío USB de la factura.');
        }
    }
}
