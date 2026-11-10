<?php

namespace App\Sales;

use App\Entity\Product;
use App\Entity\User;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\HttpFoundation\Session\SessionInterface;

/** A session-owned draft; product prices always come from the database. */
class Cart
{
    private const MAX_QUANTITY = 9999;
    private const MAX_LINES = 100;

    public function __construct(private readonly EntityManagerInterface $entityManager)
    {
    }

    private function key(User $user): string { return 'sales.cart.'.$user->getId(); }

    public function read(SessionInterface $session, User $user): array
    {
        $quantities = $session->get($this->key($user), []);
        $items = [];
        $total = 0;
        $units = 0;
        if ($quantities) {
            $products = $this->entityManager->getRepository(Product::class)->findBy(['id' => array_keys($quantities)]);
            $byId = [];
            foreach ($products as $product) $byId[$product->getId()] = $product;
            foreach ($quantities as $id => $quantity) {
                if (!isset($byId[$id])) continue;
                $product = $byId[$id];
                $parts = explode('.', $product->getSalePrice());
                $cents = (int) $parts[0] * 100 + (int) str_pad($parts[1] ?? '', 2, '0');
                $subtotal = $cents * $quantity;
                $total += $subtotal;
                $units += $quantity;
                $items[] = ['product_id' => $product->getId(), 'name' => $product->getName(),
                    'barcode' => $product->getBarcode(), 'unit_price' => self::money($cents),
                    'quantity' => $quantity, 'subtotal' => self::money($subtotal)];
            }
        }
        // Drop deleted products instead of charging a stale catalog snapshot.
        $valid = [];
        foreach ($items as $item) $valid[$item['product_id']] = $item['quantity'];
        $removed = count($valid) !== count($quantities);
        $session->set($this->key($user), $valid);

        return ['items' => $items, 'line_count' => count($items), 'quantity' => $units,
            'total' => self::money($total), 'checkout_key' => $this->checkoutKey($session, $user), 'removed_unavailable' => $removed];
    }

    public function scan(SessionInterface $session, User $user, string $barcode): array
    {
        $product = $this->entityManager->getRepository(Product::class)->findOneBy(['barcode' => $barcode]);
        if (!$product) throw new CartException(404, 'No encontramos un producto con ese código de barras.');
        $this->read($session, $user);
        $quantities = $session->get($this->key($user), []);
        $id = $product->getId();
        if (!isset($quantities[$id]) && count($quantities) >= self::MAX_LINES) {
            throw new CartException(422, 'El carrito admite hasta 100 productos diferentes.');
        }
        $quantity = ($quantities[$id] ?? 0) + 1;
        if ($quantity > self::MAX_QUANTITY) throw new CartException(422, 'La cantidad máxima por producto es 9999.');
        $quantities[$id] = $quantity;
        $session->set($this->key($user), $quantities);
        $session->remove($this->key($user).'.checkout');

        return $this->read($session, $user);
    }

    public function update(SessionInterface $session, User $user, int $id, int $quantity): array
    {
        if ($quantity < 1 || $quantity > self::MAX_QUANTITY) throw new CartException(422, 'La cantidad debe estar entre 1 y 9999.');
        $quantities = $session->get($this->key($user), []);
        if (!isset($quantities[$id]) || !$this->entityManager->find(Product::class, $id)) throw new CartException(404, 'El producto ya no está en el carrito.');
        $quantities[$id] = $quantity;
        $session->set($this->key($user), $quantities);
        $session->remove($this->key($user).'.checkout');

        return $this->read($session, $user);
    }

    public function remove(SessionInterface $session, User $user, int $id): array
    {
        $quantities = $session->get($this->key($user), []);
        if (!isset($quantities[$id])) throw new CartException(404, 'El producto ya no está en el carrito.');
        unset($quantities[$id]);
        $session->set($this->key($user), $quantities);
        $session->remove($this->key($user).'.checkout');

        return $this->read($session, $user);
    }

    public function clear(SessionInterface $session, User $user): array
    {
        $session->remove($this->key($user));
        $session->remove($this->key($user).'.checkout');
        return $this->read($session, $user);
    }

    private function checkoutKey(SessionInterface $session, User $user): string
    {
        $key = $this->key($user).'.checkout';
        if (!$session->has($key)) $session->set($key, bin2hex(random_bytes(16)));
        return $session->get($key);
    }

    private static function money(int $cents): string
    {
        return intdiv($cents, 100).'.'.str_pad((string) ($cents % 100), 2, '0', STR_PAD_LEFT);
    }
}
