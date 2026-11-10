<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110070000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Ficha única de empresa y sus permisos de acceso.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE company (id INT NOT NULL, name VARCHAR(180) NOT NULL, address VARCHAR(255) NOT NULL, phone VARCHAR(40) NOT NULL, nit VARCHAR(40) NOT NULL, PRIMARY KEY (id), CONSTRAINT company_singleton CHECK (id = 1)) DEFAULT CHARACTER SET utf8mb4');
        foreach (['view', 'create', 'update', 'delete'] as $action) {
            $this->addSql('INSERT INTO permission (module, action) VALUES (?, ?) ON DUPLICATE KEY UPDATE id = id', ['company', $action]);
        }
    }

    public function down(Schema $schema): void
    {
        $this->addSql("DELETE gp FROM group_permission gp JOIN permission p ON p.id = gp.permission_id WHERE p.module = 'company'");
        $this->addSql("DELETE FROM permission WHERE module = 'company'");
        $this->addSql('DROP TABLE company');
    }
}
