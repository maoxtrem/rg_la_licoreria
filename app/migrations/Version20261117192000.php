<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261117192000 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Registra retiros manuales de existencias.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE inventory_removal (id INT AUTO_INCREMENT NOT NULL, inventory_id INT NOT NULL, created_by INT NOT NULL, quantity INT NOT NULL, created_at DATETIME NOT NULL, INDEX IDX_removal_inventory (inventory_id), INDEX IDX_removal_user (created_by), PRIMARY KEY(id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('ALTER TABLE inventory_removal ADD CONSTRAINT FK_removal_inventory FOREIGN KEY (inventory_id) REFERENCES inventory (id) ON DELETE RESTRICT, ADD CONSTRAINT FK_removal_user FOREIGN KEY (created_by) REFERENCES app_user (id) ON DELETE RESTRICT');
        $this->addSql('ALTER TABLE inventory_removal ADD CONSTRAINT CHK_removal_quantity CHECK (quantity > 0)');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('DROP TABLE inventory_removal');
    }
}
