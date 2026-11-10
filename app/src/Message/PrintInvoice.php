<?php

namespace App\Message;

final readonly class PrintInvoice
{
    public function __construct(public string $jobId, public array $invoice) {}
}
