<?php

namespace App\Controller;

use App\Http\ApiInput;
use App\Inventory\InventoryService;
use App\Sales\CartException;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;

#[Route('/api/inventory', defaults: ['_format' => 'json', '_permission_module' => 'inventory'])]
class ApiInventoryController extends AbstractController
{
    public function __construct(private readonly InventoryService $inventory, private readonly ApiInput $input)
    {
    }

    #[Route('', name: 'api_inventory_list', methods: ['GET'])]
    public function index(Request $request): JsonResponse
    {
        $pagination = $this->input->pagination($request);
        $search = trim((string) $request->query->get('search', ''));
        $result = $this->inventory->list($pagination['page'], $pagination['limit'], $search);
        return $this->json(['data' => $result['data'], 'pagination' => [
            'page' => $pagination['page'], 'limit' => $pagination['limit'], 'total' => $result['total'],
        ]], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{productId}', name: 'api_inventory_update', defaults: ['_permission_action' => 'update'], requirements: ['productId' => '\\d+'], methods: ['PATCH'])]
    public function update(int $productId, Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'inventory');
        if (array_keys($data) !== ['active', 'stock'] || !is_bool($data['active']) || !is_int($data['stock'])) {
            throw new CartException(422, 'Incluye active como booleano y stock como entero no negativo.');
        }
        $this->inventory->setProduct($productId, $data['active'], $data['stock']);
        return $this->json(['status' => 'ok'], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{productId}/receipts', name: 'api_inventory_receipt', defaults: ['_permission_action' => 'update'], requirements: ['productId' => '\\d+'], methods: ['POST'])]
    public function receipt(int $productId, Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'inventory');
        if (array_keys($data) !== ['quantity', 'total_cost'] || !is_int($data['quantity']) || !is_int($data['total_cost'])) {
            throw new CartException(422, 'Incluye quantity y total_cost como enteros.');
        }
        $result = $this->inventory->receive($productId, $data['quantity'], $data['total_cost'], $this->getUser()->getId());
        return $this->json(['data' => $result], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{productId}/removals', name: 'api_inventory_removal', defaults: ['_permission_action' => 'update'], requirements: ['productId' => '\\d+'], methods: ['POST'])]
    public function removal(int $productId, Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'inventory');
        if (array_keys($data) !== ['quantity', 'reason'] || !is_int($data['quantity']) || !is_string($data['reason'])) {
            throw new CartException(422, 'Incluye quantity como entero y reason como texto.');
        }
        $result = $this->inventory->remove($productId, $data['quantity'], $data['reason'], $this->getUser()->getId());
        return $this->json(['data' => $result], headers: ['Cache-Control' => 'no-store']);
    }
}
