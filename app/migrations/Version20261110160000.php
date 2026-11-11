<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110160000 extends AbstractMigration
{
    public function getDescription(): string { return 'Importe transferido y soporte de pagos mixtos en la factura.'; }
    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE invoice ADD transfer_received NUMERIC(20, 2) DEFAULT NULL');
        $this->addSql("UPDATE invoice SET transfer_received = CASE WHEN payment_method = 'transfer' THEN total ELSE 0 END WHERE payment_method IN ('cash', 'transfer')");
    }
    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE invoice DROP transfer_received');
    }
}
