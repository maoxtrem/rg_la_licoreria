<?php

namespace App\Billing;

use App\Entity\Company;
use App\Entity\Invoice;
use App\Entity\Product;
use App\Entity\User;
use App\Sales\Cart;
use App\Sales\CartException;
use Doctrine\DBAL\LockMode;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\HttpFoundation\Session\SessionInterface;

class Invoicing
{
    public function __construct(private readonly EntityManagerInterface $em, private readonly Cart $cart) {}

    public function checkout(SessionInterface $session, User $user, array $data): Invoice
    {
        $expected = ($data['status'] ?? null) === 'paid' ? $this->paymentFields($data, ['status', 'checkout_key']) : ['status', 'checkout_key'];
        if (count($data) !== count($expected) || array_diff(array_keys($data), $expected) || !isset($data['status'], $data['checkout_key'])
            || !in_array($data['status'], ['pending', 'paid'], true)
            || !is_string($data['checkout_key']) || !preg_match('/^[a-f0-9]{32}$/D', $data['checkout_key'])) {
            throw new CartException(422, 'Incluye status (pending o paid), checkout_key y, al pagar, cash_received y transfer_received con dos decimales.');
        }
        $existing = $this->em->getRepository(Invoice::class)->findOneBy(['checkoutKey' => $data['checkout_key']]);
        if ($existing) {
            if ($existing->getCreatedBy() !== $user->getId()) throw new CartException(409, 'La referencia del carrito no es válida.');
            return $existing;
        }
        $cart = $this->cart->read($session, $user);
        if ($cart['checkout_key'] !== $data['checkout_key']) throw new CartException(409, 'El carrito cambió. Actualízalo antes de continuar.');
        if (!$cart['items'] || $cart['removed_unavailable']) throw new CartException(422, 'Revisa el carrito: debe contener productos disponibles.');
        $company = $data['status'] === 'paid' ? $this->company() : null;
        $invoice = $this->em->wrapInTransaction(function () use ($data, $user, $cart, $company): Invoice {
            $invoice = new Invoice($data['checkout_key'], $user->getId(), $cart);
            if ($company) $invoice->pay($company, $data['cash_received'] ?? null, $data['payment_method'] ?? 'cash', $data['transfer_received'] ?? null);
            $this->em->persist($invoice);
            return $invoice;
        });
        // Clear only after the database commit; a repeated checkout returns the same record.
        $this->cart->clear($session, $user);
        return $invoice;
    }

    public function change(int $id, array $data, bool $pay): Invoice
    {
        $expected = $pay ? $this->paymentFields($data, ['revision']) : ['revision', 'items'];
        if (array_diff(array_keys($data), $expected) || count($data) !== count($expected)
            || !isset($data['revision']) || !is_int($data['revision']) || $data['revision'] < 1) {
            throw new CartException(422, $pay ? 'Incluye revision como entero, cash_received y transfer_received con dos decimales.' : 'Incluye revision e items con product_id y quantity.');
        }
        return $this->em->wrapInTransaction(function () use ($id, $data, $pay): Invoice {
            $invoice = $this->em->find(Invoice::class, $id, LockMode::PESSIMISTIC_WRITE)
                ?? throw new CartException(404, 'No encontramos el registro.');
            if ($invoice->getStatus() !== 'pending') throw new CartException(409, 'La factura ya está facturada. Solo se puede imprimir.');
            if ($invoice->getRevision() !== $data['revision']) throw new CartException(409, 'El registro cambió en otra ventana. Recarga sus datos.');
            if ($pay) {
                $invoice->pay($this->company(), $data['cash_received'] ?? null, $data['payment_method'] ?? 'cash', $data['transfer_received'] ?? null);
            } else {
                [$items, $total] = $this->items($data['items'], $invoice->getItems());
                $invoice->replaceItems($items, $total);
            }
            return $invoice;
        });
    }

    private function paymentFields(array $data, array $base): array
    {
        if (array_key_exists('transfer_received', $data)) {
            if (!is_string($data['transfer_received']) || !preg_match('/^\d{1,15}\.\d{2}$/D', $data['transfer_received'])) {
                throw new CartException(422, 'Incluye transferencia como importe con dos decimales.');
            }
            return [...$base, 'cash_received', 'transfer_received'];
        }
        $method = $data['payment_method'] ?? 'cash';
        if (array_key_exists('payment_method', $data) && !in_array($data['payment_method'], ['cash', 'transfer'], true)) {
            throw new CartException(422, 'Selecciona efectivo o transferencia como método de pago.');
        }
        if (array_key_exists('payment_method', $data)) $base[] = 'payment_method';
        if ($method === 'cash') $base[] = 'cash_received';
        return $base;
    }

    private function company(): array
    {
        return $this->em->find(Company::class, 1)?->toArray()
            ?? throw new CartException(422, 'Registra los datos de Empresa antes de facturar.');
    }

    private function items(mixed $data, array $previous): array
    {
        if (!is_array($data) || !array_is_list($data) || !$data || count($data) > 100) throw new CartException(422, 'Incluye entre 1 y 100 productos.');
        $old = array_column($previous, null, 'product_id');
        $items = []; $seen = []; $total = 0;
        foreach ($data as $line) {
            if (!is_array($line) || count($line) !== 2 || !isset($line['product_id'], $line['quantity'])
                || !is_int($line['product_id']) || !is_int($line['quantity']) || $line['quantity'] < 1 || $line['quantity'] > 9999
                || isset($seen[$line['product_id']])) throw new CartException(422, 'Cada producto debe ser único e incluir product_id y quantity entre 1 y 9999.');
            $id = $line['product_id']; $seen[$id] = true;
            // Preserve agreed prices for existing lines. New products use current catalog prices.
            $item = $old[$id] ?? null;
            if (!$item) {
                $product = $this->em->find(Product::class, $id) ?? throw new CartException(422, 'El producto agregado no existe.');
                $item = ['product_id' => $id, 'name' => $product->getName(), 'barcode' => $product->getBarcode(), 'unit_price' => $product->getSalePrice()];
            }
            [$whole, $fraction] = explode('.', $item['unit_price']);
            $subtotal = ((int) $whole * 100 + (int) $fraction) * $line['quantity'];
            $item['quantity'] = $line['quantity'];
            $item['subtotal'] = self::money($subtotal);
            $total += $subtotal;
            $items[] = $item;
        }
        return [$items, self::money($total)];
    }

    private static function money(int $cents): string
    {
        return intdiv($cents, 100).'.'.str_pad((string) ($cents % 100), 2, '0', STR_PAD_LEFT);
    }
}
