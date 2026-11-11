<?php

namespace App\Billing;

use App\Entity\Invoice;
use App\Message\PrintInvoice;
use Psr\Log\LoggerInterface;
use Symfony\Component\Messenger\MessageBusInterface;

final class PaidInvoicePrinting
{
    public function __construct(private readonly MessageBusInterface $bus, private readonly LoggerInterface $logger) {}

    public function queue(Invoice $invoice): array
    {
        // A repeated checkout uses the same reference, so USB deduplication applies.
        $jobId = substr(hash('sha256', 'invoice-payment:'.$invoice->getId()), 0, 32);
        try {
            $this->bus->dispatch(new PrintInvoice($jobId, $invoice->toArray()));
            return ['status' => 'queued', 'print_job_id' => $jobId];
        } catch (\Throwable $error) {
            // Payment is already committed; never report it as a failed payment.
            $this->logger->error('Could not queue automatic invoice printing.', ['invoice_id' => $invoice->getId(), 'exception' => $error]);
            return ['status' => 'unavailable', 'print_job_id' => $jobId];
        }
    }
}
