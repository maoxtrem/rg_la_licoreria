<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110040044 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Crea productos con código de barras único y precios de venta y costo decimales.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE product (id INT AUTO_INCREMENT NOT NULL, name VARCHAR(180) NOT NULL, barcode VARCHAR(100) NOT NULL, sale_price NUMERIC(12, 2) NOT NULL, cost_price NUMERIC(12, 2) NOT NULL, UNIQUE INDEX UNIQ_D34A04AD97AE0266 (barcode), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
    }

    public function down(Schema $schema): void
    {
        $this->addSql('DROP TABLE product');
    }
}
