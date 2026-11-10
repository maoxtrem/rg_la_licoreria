<?php

namespace App\Entity;

use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'permission')]
#[ORM\UniqueConstraint(name: 'permission_module_action', columns: ['module', 'action'])]
class Permission
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    private ?int $id = null;

    #[ORM\Column(length: 60)]
    private string $module;

    #[ORM\Column(length: 20)]
    private string $action;

    public function getId(): ?int { return $this->id; }
    public function getModule(): string { return $this->module; }
    public function getAction(): string { return $this->action; }
    public function getKey(): string { return $this->module.'.'.$this->action; }
}
