<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110150000 extends AbstractMigration
{
    public function getDescription(): string { return 'Método de pago en efectivo o transferencia en la factura.'; }
    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE invoice ADD payment_method VARCHAR(20) DEFAULT NULL');
        $this->addSql("UPDATE invoice SET payment_method = 'cash' WHERE status = 'paid' AND cash_received IS NOT NULL");
    }
    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE invoice DROP payment_method');
    }
}
