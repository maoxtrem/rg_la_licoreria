<?php

namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'company')]
class Company
{
    #[ORM\Id]
    #[ORM\Column]
    private int $id = 1;

    #[ORM\Column(length: 180)]
    private string $name;

    #[ORM\Column(length: 255)]
    private string $address;

    #[ORM\Column(length: 40)]
    private string $phone;

    #[ORM\Column(length: 40)]
    private string $nit;

    public function __construct(array $values) { $this->update($values); }

    public function update(array $values): void
    {
        $this->name = $values['name'];
        $this->address = $values['address'];
        $this->phone = $values['phone'];
        $this->nit = $values['nit'];
    }

    public function toArray(): array
    {
        return ['name' => $this->name, 'address' => $this->address, 'phone' => $this->phone, 'nit' => $this->nit];
    }
}
