<?php

namespace App\Controller;

use App\Billing\Invoicing;
use App\Entity\Invoice;
use App\Http\ApiInput;
use App\Message\PrintInvoice;
use App\Sales\CartException;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Messenger\MessageBusInterface;
use Symfony\Component\Routing\Attribute\Route;

#[Route('/api/billing', defaults: ['_format' => 'json', '_permission_module' => 'billing'])]
class ApiBillingController extends AbstractController
{
    public function __construct(private readonly EntityManagerInterface $em, private readonly Invoicing $invoicing, private readonly ApiInput $input) {}

    #[Route('', name: 'api_billing_list', methods: ['GET'])]
    public function index(Request $request): JsonResponse
    {
        $pagination = $this->input->pagination($request);
        $status = $request->query->get('status');
        if ($status !== null && !in_array($status, ['pending', 'paid'], true)) throw new CartException(422, 'Estado no válido.');
        $criteria = $status ? ['status' => $status] : [];
        $repository = $this->em->getRepository(Invoice::class);
        return $this->json(['data' => array_map(fn (Invoice $invoice) => $invoice->toArray(), $repository->findBy($criteria, ['id' => 'DESC'], $pagination['limit'], $pagination['offset'])),
            'pagination' => ['page' => $pagination['page'], 'limit' => $pagination['limit'], 'total' => $repository->count($criteria)]], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}', name: 'api_billing_show', requirements: ['id' => '\d+'], methods: ['GET'])]
    public function show(int $id): JsonResponse
    {
        return $this->json(['data' => $this->find($id)->toArray()], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}', name: 'api_billing_edit', requirements: ['id' => '\d+'], methods: ['PATCH'])]
    public function edit(int $id, Request $request): JsonResponse
    {
        $invoice = $this->invoicing->change($id, $this->input->read($request, 'billing'), false);
        return $this->json(['data' => $invoice->toArray()], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}/pay', name: 'api_billing_pay', defaults: ['_permission_action' => 'update'], requirements: ['id' => '\d+'], methods: ['POST'])]
    public function pay(int $id, Request $request): JsonResponse
    {
        $invoice = $this->invoicing->change($id, $this->input->read($request, 'billing'), true);
        return $this->json(['data' => $invoice->toArray()], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}/print', name: 'api_billing_print', defaults: ['_permission_action' => 'view'], requirements: ['id' => '\d+'], methods: ['POST'])]
    public function printInvoice(int $id, Request $request, MessageBusInterface $bus): JsonResponse
    {
        $data = $this->input->read($request, 'billing');
        if (array_keys($data) !== ['print_job_id'] || !is_string($data['print_job_id'])
            || !preg_match('/^[a-f0-9]{32}$/D', $data['print_job_id'])) throw new CartException(422, 'Incluye print_job_id como referencia de 32 caracteres hexadecimales.');
        $invoice = $this->find($id);
        if ($invoice->getStatus() !== 'paid') throw new CartException(409, 'Solo se pueden imprimir facturas facturadas.');
        $bus->dispatch(new PrintInvoice($data['print_job_id'], $invoice->toArray()));
        return $this->json(['status' => 'queued', 'print_job_id' => $data['print_job_id']], 202, ['Cache-Control' => 'no-store']);
    }

    private function find(int $id): Invoice
    {
        return $this->em->find(Invoice::class, $id) ?? throw $this->createNotFoundException();
    }
}
