<?php

namespace App\Controller;

use App\Entity\Product;
use App\Product\ProductInput;
use App\Storage\ProductImages;
use App\Repository\ProductRepository;
use Doctrine\DBAL\Exception\UniqueConstraintViolationException;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Exception\JsonException;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\Exception\BadRequestHttpException;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\Security\Http\Attribute\IsGranted;

#[Route('/api/products', defaults: ['_format' => 'json', '_permission_module' => 'products'])]
#[IsGranted('ROLE_USER')]
class ApiProductController extends AbstractController
{
    public function __construct(
        private readonly ProductRepository $products,
        private readonly EntityManagerInterface $entityManager,
        private readonly ProductInput $input,
        private readonly ProductImages $images,
    ) {
    }

    #[Route('', name: 'api_products_list', methods: ['GET'])]
    public function index(Request $request): JsonResponse
    {
        $page = filter_var($request->query->get('page', '1'), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $limit = filter_var($request->query->get('limit', '20'), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 100]]);
        if ($page === false || $limit === false || $page > intdiv(PHP_INT_MAX, $limit)) {
            throw new BadRequestHttpException();
        }
        $barcode = trim($request->query->get('barcode', ''));
        $criteria = $barcode === '' ? [] : ['barcode' => $barcode];
        $products = $this->products->findBy($criteria, ['id' => 'DESC'], $limit, ($page - 1) * $limit);

        return $this->json([
            'data' => array_map($this->serialize(...), $products),
            'pagination' => ['page' => $page, 'limit' => $limit, 'total' => $this->products->count($criteria)],
        ], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}', name: 'api_products_show', requirements: ['id' => '\d+'], methods: ['GET'])]
    public function show(int $id): JsonResponse
    {
        return $this->json(['data' => $this->serialize($this->find($id))], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('', name: 'api_products_create', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $this->checkCsrf($request);
        $result = $this->input->validate($this->payload($request));
        if ($result['errors']) return $this->validationError($result['errors']);
        $values = $result['values'];
        if ($this->products->findOneBy(['barcode' => $values['barcode']])) return $this->barcodeConflict();

        $product = new Product($values['name'], $values['barcode'], $values['sale_price'], $values['cost_price']);
        $this->entityManager->persist($product);
        if ($error = $this->save($product, $request)) return $error;

        return $this->json(['data' => $this->serialize($product)], Response::HTTP_CREATED, [
            'Location' => $this->generateUrl('api_products_show', ['id' => $product->getId()]),
            'Cache-Control' => 'no-store',
        ]);
    }

    #[Route('/{id}', name: 'api_products_update_upload', defaults: ['_permission_action' => 'update'], requirements: ['id' => '\d+'], methods: ['POST'])]
    #[Route('/{id}', name: 'api_products_update', requirements: ['id' => '\d+'], methods: ['PUT', 'PATCH'])]
    public function update(int $id, Request $request): JsonResponse
    {
        $this->checkCsrf($request);
        $product = $this->find($id);
        $result = $this->input->validate($this->payload($request), $request->isMethod('PATCH'));
        if ($result['errors']) return $this->validationError($result['errors']);
        $values = $result['values'] + $this->serialize($product);
        $existing = $this->products->findOneBy(['barcode' => $values['barcode']]);
        if ($existing && $existing->getId() !== $product->getId()) return $this->barcodeConflict();

        $product->update($values['name'], $values['barcode'], $values['sale_price'], $values['cost_price']);
        if ($error = $this->save($product, $request)) return $error;

        return $this->json(['data' => $this->serialize($product)], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('/{id}', name: 'api_products_delete', requirements: ['id' => '\d+'], methods: ['DELETE'])]
    public function delete(int $id, Request $request): Response
    {
        $this->checkCsrf($request);
        $product = $this->find($id);
        $imageKey = $product->getImageKey();
        $this->entityManager->remove($product);
        $this->entityManager->flush();

        if ($imageKey) $this->images->delete($imageKey);
        return new Response(status: Response::HTTP_NO_CONTENT);
    }

    #[Route('/{id}/image', name: 'api_products_image', defaults: ['_permission_action' => 'view'], requirements: ['id' => '\d+'], methods: ['GET'])]
    public function image(int $id): Response
    {
        $key = $this->find($id)->getImageKey() ?? throw $this->createNotFoundException();
        $image = $this->images->read($key);
        return new Response($image['body'], 200, [
            'Content-Type' => $image['type'], 'Cache-Control' => 'private, no-store',
            'X-Content-Type-Options' => 'nosniff',
        ]);
    }

    private function save(Product $product, Request $request): ?JsonResponse
    {
        $file = $request->files->get('image');
        if ($file !== null && (!$file instanceof \Symfony\Component\HttpFoundation\File\UploadedFile || $this->images->invalid($file))) {
            return $this->validationError(['image' => 'Selecciona una imagen JPG, PNG o WebP válida de hasta 2 MB y 20 megapíxeles.']);
        }
        $oldKey = $product->getImageKey();
        $newKey = null;
        if ($file) {
            try {
                $newKey = $this->images->upload($file);
                $product->setImageKey($newKey);
            } catch (\Throwable) {
                return $this->json(['error' => 'No se pudo guardar la imagen en MinIO. Inténtalo nuevamente.'], 503);
            }
        }
        try {
            $this->entityManager->flush();
        } catch (\Throwable $exception) {
            if ($newKey) $this->images->delete($newKey);
            if ($exception instanceof UniqueConstraintViolationException) return $this->barcodeConflict();
            throw $exception;
        }
        if ($newKey && $oldKey) $this->images->delete($oldKey);
        return null;
    }

    private function checkCsrf(Request $request): void
    {
        if (!$this->isCsrfTokenValid('products', $request->headers->get('X-CSRF-Token'))) {
            throw new AccessDeniedHttpException();
        }
    }

    private function payload(Request $request): array
    {
        try {
            $multipart = $request->getContentTypeFormat() === 'form';
            $content = $multipart ? $request->request->get('data', '') : $request->getContent();
            $data = $multipart ? json_decode($content, true, 512, JSON_THROW_ON_ERROR) : $request->toArray();
        } catch (JsonException|\JsonException $exception) {
            throw new BadRequestHttpException(previous: $exception);
        }
        if (!str_starts_with(ltrim($content), '{') || !is_array($data)) throw new BadRequestHttpException();

        return $data;
    }

    private function find(int $id): Product
    {
        return $this->products->find($id) ?? throw $this->createNotFoundException();
    }

    private function serialize(Product $product): array
    {
        return [
            'id' => $product->getId(),
            'name' => $product->getName(),
            'barcode' => $product->getBarcode(),
            'sale_price' => $product->getSalePrice(),
            'cost_price' => $product->getCostPrice(),
            'image_url' => $product->getImageKey() ? $this->generateUrl('api_products_image', ['id' => $product->getId(), 'v' => basename($product->getImageKey())]) : null,
        ];
    }

    private function validationError(array $errors): JsonResponse
    {
        return $this->json(['error' => 'Revisa los datos del producto.', 'errors' => $errors], Response::HTTP_UNPROCESSABLE_ENTITY);
    }

    private function barcodeConflict(): JsonResponse
    {
        return $this->json(['error' => 'Ya existe un producto con ese código de barras.', 'errors' => ['barcode' => 'El código de barras debe ser único.']], Response::HTTP_CONFLICT);
    }
}
