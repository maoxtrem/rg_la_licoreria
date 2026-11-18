<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261117180000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Costo promedio del inventario y registro de entradas de mercancía.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('ALTER TABLE inventory ADD average_cost NUMERIC(20, 2) NOT NULL DEFAULT 0');
        $this->addSql('CREATE TABLE inventory_receipt (id INT AUTO_INCREMENT NOT NULL, inventory_id INT NOT NULL, created_by INT NOT NULL, quantity INT NOT NULL, total_cost NUMERIC(20, 2) NOT NULL, resulting_average_cost NUMERIC(20, 2) NOT NULL, created_at DATETIME NOT NULL, INDEX IDX_receipt_inventory (inventory_id), INDEX IDX_receipt_user (created_by), PRIMARY KEY(id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('ALTER TABLE inventory_receipt ADD CONSTRAINT FK_receipt_inventory FOREIGN KEY (inventory_id) REFERENCES inventory (id) ON DELETE RESTRICT, ADD CONSTRAINT FK_receipt_user FOREIGN KEY (created_by) REFERENCES app_user (id) ON DELETE RESTRICT');
        $this->addSql('ALTER TABLE inventory_receipt ADD CONSTRAINT CHK_receipt_quantity CHECK (quantity > 0), ADD CONSTRAINT CHK_receipt_cost CHECK (total_cost >= 0)');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('DROP TABLE inventory_receipt');
        $this->addSql('ALTER TABLE inventory DROP average_cost');
    }
}
