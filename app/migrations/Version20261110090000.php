<?php

declare(strict_types=1);
namespace DoctrineMigrations;
use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110090000 extends AbstractMigration
{
    public function getDescription(): string { return 'Registros pendientes y facturas cerradas con detalle y empresa congelados.'; }
    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE invoice (id INT AUTO_INCREMENT NOT NULL, checkout_key VARCHAR(36) NOT NULL, created_by INT NOT NULL, status VARCHAR(20) NOT NULL, items JSON NOT NULL, total NUMERIC(20, 2) NOT NULL, company JSON DEFAULT NULL, revision INT NOT NULL, created_at DATETIME NOT NULL, paid_at DATETIME DEFAULT NULL, UNIQUE INDEX UNIQ_invoice_checkout (checkout_key), PRIMARY KEY(id)) DEFAULT CHARACTER SET utf8mb4');
    }
    public function down(Schema $schema): void { $this->addSql('DROP TABLE invoice'); }
}
