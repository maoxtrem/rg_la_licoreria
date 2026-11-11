<?php

namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'invoice')]
#[ORM\UniqueConstraint(name: 'UNIQ_invoice_checkout', columns: ['checkout_key'])]
class Invoice
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    private ?int $id = null;
    #[ORM\Column(length: 36)]
    private string $checkoutKey;
    #[ORM\Column]
    private int $createdBy;
    #[ORM\Column(length: 20)]
    private string $status = 'pending';
    #[ORM\Column(type: 'json')]
    private array $items;
    #[ORM\Column(type: 'decimal', precision: 20, scale: 2)]
    private string $total;
    #[ORM\Column(type: 'json', nullable: true)]
    private ?array $company = null;
    #[ORM\Column]
    private int $revision = 1;
    #[ORM\Column]
    private \DateTimeImmutable $createdAt;
    #[ORM\Column(nullable: true)]
    private ?\DateTimeImmutable $paidAt = null;
    #[ORM\Column(type: 'decimal', precision: 20, scale: 2, nullable: true)]
    private ?string $cashReceived = null;
    #[ORM\Column(type: 'decimal', precision: 20, scale: 2, nullable: true)]
    private ?string $changeDue = null;
    #[ORM\Column(length: 20, nullable: true)]
    private ?string $paymentMethod = null;
    #[ORM\Column(type: 'decimal', precision: 20, scale: 2, nullable: true)]
    private ?string $transferReceived = null;

    public function __construct(string $checkoutKey, int $createdBy, array $cart)
    {
        $this->checkoutKey = $checkoutKey;
        $this->createdBy = $createdBy;
        // Store sale data, never live catalog URLs or an ORM relation to Product.
        // product_id is only a historical reference for editing pending quantities.
        $this->items = array_map(static fn (array $item) => array_intersect_key($item, array_flip([
            'product_id', 'name', 'barcode', 'unit_price', 'quantity', 'subtotal',
        ])), $cart['items']);
        $this->total = $cart['total'];
        $this->createdAt = new \DateTimeImmutable('now', new \DateTimeZone('UTC'));
    }

    public function getId(): ?int { return $this->id; }
    public function getCreatedBy(): int { return $this->createdBy; }
    public function getStatus(): string { return $this->status; }
    public function getRevision(): int { return $this->revision; }
    public function getItems(): array { return $this->items; }

    public function replaceItems(array $items, string $total): void
    {
        $this->assertPending();
        $this->items = $items;
        $this->total = $total;
        ++$this->revision;
    }

    public function pay(array $company, mixed $cashReceived, mixed $paymentMethod = 'cash', mixed $transferReceived = null): void
    {
        $this->assertPending();
        $split = $transferReceived !== null;
        if (!$split && !in_array($paymentMethod, ['cash', 'transfer'], true)) {
            throw new \App\Sales\CartException(422, 'Selecciona efectivo o transferencia como método de pago.');
        }
        $legacyTransfer = !$split && $paymentMethod === 'transfer';
        if ($legacyTransfer && $cashReceived !== null) throw new \App\Sales\CartException(422, 'Una transferencia no recibe efectivo ni genera cambio.');
        $cash = $legacyTransfer ? '0.00' : $cashReceived;
        $transfer = $split ? $transferReceived : ($legacyTransfer ? $this->total : '0.00');
        $cents = static function (mixed $value): int {
            if (!is_string($value) || !preg_match('/^\d{1,15}\.\d{2}$/D', $value)) {
                throw new \App\Sales\CartException(422, 'Incluye efectivo y transferencia como importes con dos decimales.');
            }
            [$whole, $fraction] = explode('.', $value);
            return (int) $whole * 100 + (int) $fraction;
        };
        $cashCents = $cents($cash);
        $transferCents = $cents($transfer);
        $total = $cents($this->total);
        if ($transferCents > $total) throw new \App\Sales\CartException(422, 'La transferencia no puede superar el total de la factura.');
        $change = $cashCents + $transferCents - $total;
        if ($change < 0) throw new \App\Sales\CartException(422, 'El efectivo y la transferencia no cubren el total.');
        $money = static fn (int $value): string => intdiv($value, 100).'.'.str_pad((string) ($value % 100), 2, '0', STR_PAD_LEFT);
        $this->cashReceived = $legacyTransfer ? null : $money($cashCents);
        $this->changeDue = $legacyTransfer ? null : $money($change);
        $this->transferReceived = $money($transferCents);
        $this->paymentMethod = $transferCents === 0 ? 'cash' : ($cashCents === 0 ? 'transfer' : 'mixed');
        $this->company = $company;
        $this->status = 'paid';
        $this->paidAt = new \DateTimeImmutable('now', new \DateTimeZone('UTC'));
        ++$this->revision;
    }

    private function assertPending(): void
    {
        if ($this->status !== 'pending') throw new \App\Sales\CartException(409, 'La factura ya está facturada y no se puede editar ni cobrar nuevamente.');
    }

    public function toArray(): array
    {
        return ['id' => $this->id, 'number' => 'F-'.str_pad((string) $this->id, 6, '0', STR_PAD_LEFT),
            'status' => $this->status, 'items' => $this->items, 'total' => $this->total,
            'company' => $this->company, 'revision' => $this->revision,
            'cash_received' => $this->cashReceived, 'change_due' => $this->changeDue,
            'payment_method' => $this->paymentMethod, 'transfer_received' => $this->transferReceived,
            'created_at' => $this->createdAt->format(DATE_ATOM), 'paid_at' => $this->paidAt?->format(DATE_ATOM)];
    }
}
