<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110140000 extends AbstractMigration
{
    public function getDescription(): string { return 'Dinero recibido y cambio calculado al pagar una factura.'; }
    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE invoice ADD cash_received NUMERIC(20, 2) DEFAULT NULL, ADD change_due NUMERIC(20, 2) DEFAULT NULL');
    }
    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE invoice DROP cash_received, DROP change_due');
    }
}
