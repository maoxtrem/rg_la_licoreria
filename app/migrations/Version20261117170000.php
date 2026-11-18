<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261117170000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Inventario opcional por producto y reservas de carritos o facturas pendientes.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE inventory (id INT AUTO_INCREMENT NOT NULL, product_id INT NOT NULL, stock INT NOT NULL DEFAULT 0, active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, UNIQUE INDEX UNIQ_inventory_product (product_id), PRIMARY KEY(id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('ALTER TABLE inventory ADD CONSTRAINT FK_inventory_product FOREIGN KEY (product_id) REFERENCES product (id) ON DELETE RESTRICT');
        $this->addSql('CREATE TABLE inventory_reservation (id INT AUTO_INCREMENT NOT NULL, product_id INT NOT NULL, invoice_id INT DEFAULT NULL, cart_token VARCHAR(32) DEFAULT NULL, quantity INT NOT NULL, expires_at DATETIME DEFAULT NULL, created_at DATETIME NOT NULL, INDEX IDX_reservation_product (product_id), INDEX IDX_reservation_invoice (invoice_id), INDEX IDX_reservation_expiry (expires_at), UNIQUE INDEX UNIQ_reservation_cart_product (cart_token, product_id), UNIQUE INDEX UNIQ_reservation_invoice_product (invoice_id, product_id), PRIMARY KEY(id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('ALTER TABLE inventory_reservation ADD CONSTRAINT FK_reservation_product FOREIGN KEY (product_id) REFERENCES product (id) ON DELETE RESTRICT, ADD CONSTRAINT FK_reservation_invoice FOREIGN KEY (invoice_id) REFERENCES invoice (id) ON DELETE CASCADE');
        $this->addSql('ALTER TABLE inventory_reservation ADD CONSTRAINT CHK_reservation_quantity CHECK (quantity > 0)');
        $this->addSql('ALTER TABLE inventory ADD CONSTRAINT CHK_inventory_stock CHECK (stock >= 0)');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('DROP TABLE inventory_reservation');
        $this->addSql('DROP TABLE inventory');
    }
}
