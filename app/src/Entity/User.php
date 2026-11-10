<?php

namespace App\Entity;

use App\Repository\UserRepository;
use Doctrine\ORM\Mapping as ORM;
use Symfony\Component\Security\Core\User\PasswordAuthenticatedUserInterface;
use Symfony\Component\Security\Core\User\UserInterface;

#[ORM\Entity(repositoryClass: UserRepository::class)]
#[ORM\Table(name: 'app_user')]
class User implements UserInterface, PasswordAuthenticatedUserInterface
{
    public const ROLE_ADMIN = 'ROLE_ADMIN';
    public const ROLE_USER = 'ROLE_USER';

    #[ORM\Id]
    #[ORM\GeneratedValue]
    #[ORM\Column]
    private ?int $id = null;

    #[ORM\Column(length: 180, unique: true)]
    private string $username;

    /** @var list<string> */
    #[ORM\Column(type: 'json')]
    private array $roles = [];

    #[ORM\Column]
    private string $password;

    #[ORM\ManyToOne(targetEntity: UserGroup::class)]
    #[ORM\JoinColumn(name: 'group_id', nullable: true, onDelete: 'RESTRICT')]
    private ?UserGroup $group = null;

    public function getGroup(): ?UserGroup { return $this->group; }
    public function setGroup(?UserGroup $group): void { $this->group = $group; }

    /** @param list<string> $roles */
    public function __construct(string $username, array $roles = [self::ROLE_USER])
    {
        $this->username = $username;
        $this->setRoles($roles);
    }

    public function getId(): ?int
    {
        return $this->id;
    }

    public function getUsername(): string
    {
        return $this->username;
    }

    public function getUserIdentifier(): string
    {
        return $this->username;
    }

    /** @return list<string> */
    public function getRoles(): array
    {
        return array_values(array_unique([...$this->roles, self::ROLE_USER]));
    }

    /** @param list<string> $roles */
    public function setRoles(array $roles): void
    {
        foreach ($roles as $role) {
            if (!in_array($role, [self::ROLE_ADMIN, self::ROLE_USER], true)) {
                throw new \InvalidArgumentException('Rol no permitido.');
            }
        }

        $this->roles = array_values(array_unique($roles));
    }

    public function getPassword(): string
    {
        return $this->password;
    }

    public function setPassword(string $password): void
    {
        $this->password = $password;
    }

    public function eraseCredentials(): void
    {
    }

    public function __serialize(): array
    {
        $data = (array) $this;
        unset($data["\0".self::class."\0group"]);
        $data["\0".self::class."\0password"] = hash('crc32c', $this->password);

        return $data;
    }
}
