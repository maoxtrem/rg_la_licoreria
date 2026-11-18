<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261117193000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Agrega el motivo obligatorio a los retiros de inventario.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE inventory_removal ADD reason VARCHAR(255) NOT NULL AFTER quantity');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE inventory_removal DROP reason');
    }
}
