<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110120000 extends AbstractMigration
{
    public function getDescription(): string { return 'Imagen opcional de producto almacenada en MinIO.'; }
    public function up(Schema $schema): void { $this->addSql('ALTER TABLE product ADD image_key VARCHAR(255) DEFAULT NULL'); }
    public function down(Schema $schema): void { $this->addSql('ALTER TABLE product DROP image_key'); }
}
