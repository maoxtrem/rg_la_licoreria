<?php

namespace App\Entity;

use App\Repository\ProductRepository;
use Doctrine\DBAL\Types\Types;
use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity(repositoryClass: ProductRepository::class)]
#[ORM\Table(name: 'product')]
class Product
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    private ?int $id = null;

    #[ORM\Column(length: 180)]
    private string $name;

    #[ORM\Column(length: 100, unique: true)]
    private string $barcode;

    #[ORM\Column(type: Types::DECIMAL, precision: 12, scale: 2)]
    private string $salePrice;

    #[ORM\Column(type: Types::DECIMAL, precision: 12, scale: 2)]
    private string $costPrice;

    public function __construct(string $name, string $barcode, string $salePrice, string $costPrice)
    {
        $this->update($name, $barcode, $salePrice, $costPrice);
    }

    public function update(string $name, string $barcode, string $salePrice, string $costPrice): void
    {
        $this->name = $name;
        $this->barcode = $barcode;
        $this->salePrice = $salePrice;
        $this->costPrice = $costPrice;
    }

    public function getId(): ?int { return $this->id; }
    public function getName(): string { return $this->name; }
    public function getBarcode(): string { return $this->barcode; }
    public function getSalePrice(): string { return $this->salePrice; }
    public function getCostPrice(): string { return $this->costPrice; }
}
