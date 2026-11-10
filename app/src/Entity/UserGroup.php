<?php

namespace App\Entity;

use Doctrine\Common\Collections\ArrayCollection;
use Doctrine\Common\Collections\Collection;
use Doctrine\ORM\Mapping as ORM;

#[ORM\Entity]
#[ORM\Table(name: 'user_group')]
class UserGroup
{
    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    private ?int $id = null;

    #[ORM\Column(length: 100, unique: true)]
    private string $name;

    /** @var Collection<int, Permission> */
    #[ORM\ManyToMany(targetEntity: Permission::class)]
    #[ORM\JoinTable(name: 'group_permission')]
    #[ORM\JoinColumn(name: 'group_id', onDelete: 'CASCADE')]
    #[ORM\InverseJoinColumn(name: 'permission_id', onDelete: 'CASCADE')]
    #[ORM\OrderBy(['module' => 'ASC', 'action' => 'ASC'])]
    private Collection $permissions;

    public function __construct(string $name)
    {
        $this->name = $name;
        $this->permissions = new ArrayCollection();
    }

    public function getId(): ?int { return $this->id; }
    public function getName(): string { return $this->name; }
    public function setName(string $name): void { $this->name = $name; }

    /** @return Collection<int, Permission> */
    public function getPermissions(): Collection { return $this->permissions; }

    /** @param list<Permission> $permissions */
    public function replacePermissions(array $permissions): void
    {
        $this->permissions->clear();
        foreach ($permissions as $permission) {
            if (!$this->permissions->contains($permission)) $this->permissions->add($permission);
        }
    }
}
