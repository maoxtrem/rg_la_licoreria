<?php

namespace App\Controller;

use App\Http\ApiInput;
use App\Sales\Cart;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[Route('/api/sales/cart', defaults: ['_format' => 'json', '_permission_module' => 'sales'])]
class ApiSalesController extends AbstractController
{
    public function __construct(private readonly Cart $cart, private readonly ApiInput $input)
    {
    }

    #[Route('', name: 'api_sales_cart', methods: ['GET'])]
    public function index(Request $request): JsonResponse
    {
        return $this->result($this->cart->read($request->getSession(), $this->getUser()));
    }

    #[Route('/items', name: 'api_sales_scan', methods: ['POST'])]
    public function scan(Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'sales');
        if (array_keys($data) !== ['barcode'] || !is_string($data['barcode']) || trim($data['barcode']) === '' || mb_strlen(trim($data['barcode'])) > 100) {
            return $this->json(['error' => 'Incluye únicamente barcode como texto de entre 1 y 100 caracteres.'], 422);
        }
        return $this->result($this->cart->scan($request->getSession(), $this->getUser(), trim($data['barcode'])));
    }

    #[Route('/items/{id}', name: 'api_sales_quantity', requirements: ['id' => '\d+'], methods: ['PATCH'])]
    public function quantity(int $id, Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'sales');
        if (array_keys($data) !== ['quantity'] || !is_int($data['quantity'])) {
            return $this->json(['error' => 'Incluye únicamente quantity como entero entre 1 y 9999.'], 422);
        }
        return $this->result($this->cart->update($request->getSession(), $this->getUser(), $id, $data['quantity']));
    }

    #[Route('/items/{id}', name: 'api_sales_remove', requirements: ['id' => '\d+'], methods: ['DELETE'])]
    public function remove(int $id, Request $request): JsonResponse
    {
        $this->input->checkCsrf($request, 'sales');
        return $this->result($this->cart->remove($request->getSession(), $this->getUser(), $id));
    }

    #[Route('', name: 'api_sales_clear', methods: ['DELETE'])]
    public function clear(Request $request): JsonResponse
    {
        $this->input->checkCsrf($request, 'sales');
        return $this->result($this->cart->clear($request->getSession(), $this->getUser()));
    }

    #[Route('/checkout', name: 'api_sales_checkout', methods: ['POST'])]
    public function checkout(Request $request, \App\Billing\Invoicing $invoicing): JsonResponse
    {
        $invoice = $invoicing->checkout($request->getSession(), $this->getUser(), $this->input->read($request, 'sales'));
        return $this->json(['data' => $invoice->toArray(), 'cart' => $this->cart->read($request->getSession(), $this->getUser())], 201, ['Cache-Control' => 'no-store']);
    }

    private function result(array $data): JsonResponse
    {
        return $this->json(['data' => $data], headers: ['Cache-Control' => 'no-store']);
    }
}
