<?php

namespace App\Controller;

use App\Billing\Invoicing;
use App\Entity\Invoice;
use App\Http\ApiInput;
use App\Message\PrintInvoice;
use App\Sales\CartException;
use Doctrine\ORM\EntityManagerInterface;
use Doctrine\DBAL\Types\Types;
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
        $number = trim($request->query->get('number', ''));
        if ($number !== '') {
            if (!preg_match('/^(?:F-)?([0-9]{1,18})$/iD', $number, $match)) throw new CartException(422, 'Incluye un número de factura válido, por ejemplo F-000123 o 123.');
            $criteria['id'] = (int) $match[1];
        }
        $today = (new \DateTimeImmutable('now', new \DateTimeZone('America/Bogota')))->format('Y-m-d');
        $from = $this->filterDate($request->query->get('from', $today));
        $to = $this->filterDate($request->query->get('to', $today));
        if ($from && $to && $from > $to) throw new CartException(422, 'La fecha desde no puede ser posterior a la fecha hasta.');
        $query = $this->em->getRepository(Invoice::class)->createQueryBuilder('i');
        foreach ($criteria as $field => $value) {
            $query->andWhere('i.'.$field.' = :'.$field)->setParameter($field, $value);
        }
        $utc = new \DateTimeZone('UTC');
        if ($from) $query->andWhere('i.createdAt >= :from')->setParameter('from', $from->setTimezone($utc), Types::DATETIME_IMMUTABLE);
        if ($to) $query->andWhere('i.createdAt < :to')->setParameter('to', $to->modify('+1 day')->setTimezone($utc), Types::DATETIME_IMMUTABLE);
        $total = (clone $query)->select('COUNT(i.id)')->getQuery()->getSingleScalarResult();
        $invoices = $query->orderBy('i.id', 'DESC')->setMaxResults($pagination['limit'])->setFirstResult($pagination['offset'])->getQuery()->getResult();
        return $this->json(['data' => array_map(fn (Invoice $invoice) => $invoice->toArray(), $invoices),
            'pagination' => ['page' => $pagination['page'], 'limit' => $pagination['limit'], 'total' => (int) $total]], headers: ['Cache-Control' => 'no-store']);
    }

    private function filterDate(string $value): ?\DateTimeImmutable
    {
        if ($value === '') return null;
        $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $value, new \DateTimeZone('America/Bogota'));
        if (!$date || $date->format('Y-m-d') !== $value) throw new CartException(422, 'Incluye una fecha válida con formato AAAA-MM-DD.');
        return $date;
    }

    #[Route('/product', name: 'api_billing_product', defaults: ['_permission_action' => 'update'], methods: ['GET'])]
    public function product(Request $request): JsonResponse
    {
        $barcode = $request->query->get('barcode');
        if (!is_string($barcode) || trim($barcode) === '' || mb_strlen($barcode) > 100) throw new CartException(422, 'Incluye un código de barras válido.');
        $product = $this->em->getRepository(\App\Entity\Product::class)->findOneBy(['barcode' => trim($barcode)])
            ?? throw new CartException(404, 'No encontramos un producto con ese código de barras.');
        return $this->json(['data' => ['product_id' => $product->getId(), 'name' => $product->getName(), 'barcode' => $product->getBarcode(),
            'unit_price' => $product->getSalePrice(), 'quantity' => 1, 'subtotal' => $product->getSalePrice()]], headers: ['Cache-Control' => 'no-store']);
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
