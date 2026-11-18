<?php

namespace App\Inventory;

use App\Sales\CartException;
use Doctrine\DBAL\Connection;

final class InventoryService
{
    private const CART_HOLD_MINUTES = 60;

    public function __construct(private readonly Connection $connection)
    {
    }

    public function syncCart(string $cartToken, array $quantities): void
    {
        $this->connection->transactional(fn () => $this->syncCartInTransaction($cartToken, $quantities));
    }

    public function syncCartInTransaction(string $cartToken, array $quantities): void
    {
        $this->cleanupExpired();
        $normalized = [];
        foreach ($quantities as $productId => $quantity) {
            if ((int) $quantity > 0) $normalized[(int) $productId] = (int) $quantity;
        }
        ksort($normalized);

        foreach ($normalized as $productId => $quantity) {
            $inventory = $this->lockInventory($productId);
            if (!$inventory || !(bool) $inventory['active']) {
                $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE cart_token = ? AND product_id = ?', [$cartToken, $productId]);
                continue;
            }
            $reserved = $this->reservedForOtherOwner($productId, 'cart_token', $cartToken);
            if ($quantity > ((int) $inventory['stock'] - $reserved)) {
                throw new CartException(409, 'No hay inventario suficiente para ese producto. Revisa la cantidad disponible.');
            }
            $expiresAt = (new \DateTimeImmutable('now', new \DateTimeZone('UTC')))->modify('+'.self::CART_HOLD_MINUTES.' minutes')->format('Y-m-d H:i:s');
            $this->connection->executeStatement(
                'INSERT INTO inventory_reservation (product_id, cart_token, quantity, expires_at, created_at) VALUES (?, ?, ?, ?, UTC_TIMESTAMP())
                 ON DUPLICATE KEY UPDATE quantity = VALUES(quantity), expires_at = VALUES(expires_at)',
                [$productId, $cartToken, $quantity, $expiresAt]
            );
        }

        if ($normalized) {
            $marks = implode(',', array_fill(0, count($normalized), '?'));
            $this->connection->executeStatement(
                "DELETE FROM inventory_reservation WHERE cart_token = ? AND product_id NOT IN ($marks)",
                [$cartToken, ...array_keys($normalized)]
            );
        } else {
            $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE cart_token = ?', [$cartToken]);
        }
    }

    public function releaseCart(string $cartToken): void
    {
        $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE cart_token = ?', [$cartToken]);
    }

    public function attachCartToInvoice(int $invoiceId, string $cartToken, array $quantities): void
    {
        $this->syncCartInTransaction($cartToken, $quantities);
        $this->connection->executeStatement(
            'UPDATE inventory_reservation SET invoice_id = ?, cart_token = NULL, expires_at = NULL WHERE cart_token = ?',
            [$invoiceId, $cartToken]
        );
    }

    public function reserveInvoice(int $invoiceId, array $items): void
    {
        $this->cleanupExpired();
        $quantities = $this->quantities($items);
        ksort($quantities);
        foreach ($quantities as $productId => $quantity) {
            $inventory = $this->lockInventory($productId);
            if (!$inventory || !(bool) $inventory['active']) {
                $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE invoice_id = ? AND product_id = ?', [$invoiceId, $productId]);
                continue;
            }
            $reserved = $this->reservedForOtherOwner($productId, 'invoice_id', $invoiceId);
            if ($quantity > ((int) $inventory['stock'] - $reserved)) {
                throw new CartException(409, 'La cantidad solicitada supera el inventario disponible.');
            }
            $this->connection->executeStatement(
                'INSERT INTO inventory_reservation (product_id, invoice_id, quantity, created_at) VALUES (?, ?, ?, UTC_TIMESTAMP())
                 ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)',
                [$productId, $invoiceId, $quantity]
            );
        }
        if ($quantities) {
            $marks = implode(',', array_fill(0, count($quantities), '?'));
            $this->connection->executeStatement(
                "DELETE FROM inventory_reservation WHERE invoice_id = ? AND product_id NOT IN ($marks)",
                [$invoiceId, ...array_keys($quantities)]
            );
        } else {
            $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE invoice_id = ?', [$invoiceId]);
        }
    }

    public function consumeCart(string $cartToken, array $items): void
    {
        $this->syncCartInTransaction($cartToken, $this->quantities($items));
        $this->consumeOwner('cart_token', $cartToken, $items);
    }

    public function consumeInvoice(int $invoiceId, array $items): void
    {
        $this->reserveInvoice($invoiceId, $items);
        $this->consumeOwner('invoice_id', $invoiceId, $items);
    }

    public function releaseInvoice(int $invoiceId): void
    {
        $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE invoice_id = ?', [$invoiceId]);
    }

    /** @return array{data: list<array<string, mixed>>, total: int} */
    public function list(int $page, int $limit, string $search = ''): array
    {
        $where = '';
        $params = [];
        if ($search !== '') {
            $where = 'WHERE p.name LIKE ? OR p.barcode LIKE ?';
            $params = ['%'.$search.'%', '%'.$search.'%'];
        }
        $total = (int) $this->connection->fetchOne("SELECT COUNT(*) FROM product p $where", $params);
        $rows = $this->connection->fetchAllAssociative(
            "SELECT p.id, p.name, p.barcode, p.sale_price, p.cost_price,
                    i.id AS inventory_id, i.active, i.stock,
                    COALESCE((SELECT SUM(r.quantity) FROM inventory_reservation r WHERE r.product_id = p.id AND (r.expires_at IS NULL OR r.expires_at > UTC_TIMESTAMP())), 0) AS reserved
             FROM product p LEFT JOIN inventory i ON i.product_id = p.id
             $where ORDER BY p.name ASC, p.id ASC LIMIT ".(int) $limit." OFFSET ".((int) (($page - 1) * $limit)),
            $params
        );
        $data = array_map(static function (array $row): array {
            $managed = $row['inventory_id'] !== null && (bool) $row['active'];
            $stock = (int) ($row['stock'] ?? 0);
            $reserved = (int) $row['reserved'];
            return [
                'product_id' => (int) $row['id'], 'name' => $row['name'], 'barcode' => $row['barcode'],
                'sale_price' => (string) $row['sale_price'], 'cost_price' => (string) $row['cost_price'],
                'inventory_id' => $row['inventory_id'] === null ? null : (int) $row['inventory_id'],
                'active' => $managed, 'stock' => $stock,
                'reserved' => $managed ? $reserved : 0,
                'available' => $managed ? max(0, $stock - $reserved) : null,
                'unlimited' => !$managed,
            ];
        }, $rows);
        return ['data' => $data, 'total' => $total];
    }

    public function setProduct(int $productId, bool $active, int $stock): void
    {
        if ($stock < 0) throw new CartException(422, 'El stock no puede ser negativo.');
        $this->connection->transactional(function () use ($productId, $active, $stock): void {
            $exists = $this->connection->fetchOne('SELECT id FROM product WHERE id = ?', [$productId]);
            if ($exists === false) throw new CartException(404, 'El producto no existe.');
            $inventory = $this->lockInventory($productId);
            if (!$inventory) {
                if ($active) {
                    $now = (new \DateTimeImmutable('now', new \DateTimeZone('UTC')))->format('Y-m-d H:i:s');
                    $this->connection->executeStatement('INSERT INTO inventory (product_id, stock, active, created_at, updated_at) VALUES (?, ?, 1, ?, ?)', [$productId, $stock, $now, $now]);
                }
                return;
            }
            $reserved = (int) $this->connection->fetchOne('SELECT COALESCE(SUM(quantity), 0) FROM inventory_reservation WHERE product_id = ? AND (expires_at IS NULL OR expires_at > UTC_TIMESTAMP())', [$productId]);
            if ($active && $stock < $reserved) throw new CartException(409, 'El nuevo stock no puede ser menor que las unidades reservadas.');
            $this->connection->executeStatement('UPDATE inventory SET stock = ?, active = ?, updated_at = UTC_TIMESTAMP() WHERE product_id = ?', [$stock, $active ? 1 : 0, $productId]);
        });
    }

    /** @return array{stock: int, average_cost: string} */
    public function receive(int $productId, int $quantity, int $totalCost, int $userId): array
    {
        if ($quantity < 1) throw new CartException(422, 'La cantidad recibida debe ser mayor que cero.');
        if ($totalCost < 0) throw new CartException(422, 'El costo total no puede ser negativo.');

        return $this->connection->transactional(function () use ($productId, $quantity, $totalCost, $userId): array {
            $inventory = $this->lockInventory($productId);
            if (!$inventory || !(bool) $inventory['active']) throw new CartException(409, 'Activa el inventario del producto antes de registrar una entrada.');
            $stock = (int) $inventory['stock'];
            $product = $this->connection->fetchAssociative('SELECT cost_price FROM product WHERE id = ? FOR UPDATE', [$productId]);
            $average = (int) round((float) $product['cost_price']);
            $newStock = $stock + $quantity;
            $rawAverage = intdiv(($stock * $average) + $totalCost + $newStock - 1, $newStock);
            $newAverage = intdiv($rawAverage + 99, 100) * 100;
            $this->connection->executeStatement('UPDATE inventory SET stock = ?, updated_at = UTC_TIMESTAMP() WHERE id = ?', [$newStock, $inventory['id']]);
            $this->connection->executeStatement('UPDATE product SET cost_price = ? WHERE id = ?', [$newAverage, $productId]);
            $this->connection->executeStatement('INSERT INTO inventory_receipt (inventory_id, created_by, quantity, total_cost, resulting_average_cost, created_at) VALUES (?, ?, ?, ?, ?, UTC_TIMESTAMP())', [$inventory['id'], $userId, $quantity, $totalCost, $newAverage]);
            return ['stock' => $newStock, 'average_cost' => number_format($newAverage, 2, '.', '')];
        });
    }

    /** @return array{stock: int, reserved: int, available: int} */
    public function remove(int $productId, int $quantity, string $reason, int $userId): array
    {
        if ($quantity < 1) throw new CartException(422, 'La cantidad a retirar debe ser mayor que cero.');
        $reason = trim($reason);
        if ($reason === '') throw new CartException(422, 'El motivo del retiro es obligatorio.');
        if (mb_strlen($reason) > 255) throw new CartException(422, 'El motivo no puede superar 255 caracteres.');

        return $this->connection->transactional(function () use ($productId, $quantity, $reason, $userId): array {
            $inventory = $this->lockInventory($productId);
            if (!$inventory || !(bool) $inventory['active']) throw new CartException(409, 'El producto no tiene inventario activo.');
            $this->cleanupExpired();
            $reserved = (int) $this->connection->fetchOne(
                'SELECT COALESCE(SUM(quantity), 0) FROM inventory_reservation WHERE product_id = ? AND (expires_at IS NULL OR expires_at > UTC_TIMESTAMP())',
                [$productId]
            );
            $available = (int) $inventory['stock'] - $reserved;
            if ($quantity > $available) throw new CartException(409, 'No puedes retirar unidades reservadas. Disponible para retirar: '.$available.'.');
            $newStock = (int) $inventory['stock'] - $quantity;
            $this->connection->executeStatement('UPDATE inventory SET stock = ?, updated_at = UTC_TIMESTAMP() WHERE id = ?', [$newStock, $inventory['id']]);
            $this->connection->executeStatement('INSERT INTO inventory_removal (inventory_id, created_by, quantity, reason, created_at) VALUES (?, ?, ?, ?, UTC_TIMESTAMP())', [$inventory['id'], $userId, $quantity, $reason]);
            return ['stock' => $newStock, 'reserved' => $reserved, 'available' => $newStock - $reserved];
        });
    }

    private function consumeOwner(string $column, int|string $owner, array $items): void
    {
        $quantities = $this->quantities($items);
        foreach ($quantities as $productId => $quantity) {
            $inventory = $this->lockInventory($productId);
            if (!$inventory || !(bool) $inventory['active']) continue;
            $reserved = $this->reservedForOtherOwner($productId, $column, $owner);
            if ($quantity > ((int) $inventory['stock'] - $reserved)) throw new CartException(409, 'El inventario cambió y ya no alcanza para completar la venta.');
            $this->connection->executeStatement('UPDATE inventory SET stock = stock - ?, updated_at = UTC_TIMESTAMP() WHERE id = ?', [$quantity, $inventory['id']]);
        }
        $this->connection->executeStatement("DELETE FROM inventory_reservation WHERE $column = ?", [$owner]);
    }

    private function reservedForOtherOwner(int $productId, string $column, int|string $owner): int
    {
        $operator = $column === 'cart_token' ? '<>' : '<>';
        return (int) $this->connection->fetchOne(
            "SELECT COALESCE(SUM(quantity), 0) FROM inventory_reservation WHERE product_id = ? AND ($column IS NULL OR $column $operator ?) AND (expires_at IS NULL OR expires_at > UTC_TIMESTAMP())",
            [$productId, $owner]
        );
    }

    private function lockInventory(int $productId): ?array
    {
        $row = $this->connection->fetchAssociative('SELECT id, stock, active FROM inventory WHERE product_id = ? FOR UPDATE', [$productId]);
        return $row ?: null;
    }

    private function cleanupExpired(): void
    {
        $this->connection->executeStatement('DELETE FROM inventory_reservation WHERE cart_token IS NOT NULL AND expires_at IS NOT NULL AND expires_at <= UTC_TIMESTAMP()');
    }

    private function quantities(array $items): array
    {
        $quantities = [];
        foreach ($items as $item) {
            if (isset($item['product_id'], $item['quantity'])) $quantities[(int) $item['product_id']] = (int) $item['quantity'];
        }
        return $quantities;
    }
}
