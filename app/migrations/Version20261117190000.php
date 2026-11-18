<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261117190000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Usa el costo del producto como costo promedio único y elimina el duplicado del inventario.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE inventory DROP average_cost');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE inventory ADD average_cost NUMERIC(20, 2) NOT NULL DEFAULT 0');
    }
}
