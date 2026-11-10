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

    public function pay(array $company): void
    {
        $this->assertPending();
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
            'created_at' => $this->createdAt->format(DATE_ATOM), 'paid_at' => $this->paidAt?->format(DATE_ATOM)];
    }
}
