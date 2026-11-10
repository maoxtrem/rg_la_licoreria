<?php

declare(strict_types=1);

namespace DoctrineMigrations;

use Doctrine\DBAL\Schema\Schema;
use Doctrine\Migrations\AbstractMigration;

final class Version20261110041210 extends AbstractMigration
{
    public function getDescription(): string
    {
        return 'Grupos de usuarios y catálogo de permisos por módulo y acción.';
    }

    public function up(Schema $schema): void
    {
        $this->addSql('CREATE TABLE permission (id INT AUTO_INCREMENT NOT NULL, module VARCHAR(60) NOT NULL, action VARCHAR(20) NOT NULL, UNIQUE INDEX permission_module_action (module, action), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('CREATE TABLE user_group (id INT AUTO_INCREMENT NOT NULL, name VARCHAR(100) NOT NULL, UNIQUE INDEX UNIQ_8F02BF9D5E237E06 (name), PRIMARY KEY (id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('CREATE TABLE group_permission (group_id INT NOT NULL, permission_id INT NOT NULL, INDEX IDX_3784F318FE54D947 (group_id), INDEX IDX_3784F318FED90CCA (permission_id), PRIMARY KEY (group_id, permission_id)) DEFAULT CHARACTER SET utf8mb4');
        $this->addSql('ALTER TABLE group_permission ADD CONSTRAINT FK_3784F318FE54D947 FOREIGN KEY (group_id) REFERENCES user_group (id) ON DELETE CASCADE');
        $this->addSql('ALTER TABLE group_permission ADD CONSTRAINT FK_3784F318FED90CCA FOREIGN KEY (permission_id) REFERENCES permission (id) ON DELETE CASCADE');
        $this->addSql('ALTER TABLE app_user ADD group_id INT DEFAULT NULL');
        $this->addSql('ALTER TABLE app_user ADD CONSTRAINT FK_88BDF3E9FE54D947 FOREIGN KEY (group_id) REFERENCES user_group (id) ON DELETE RESTRICT');
        $this->addSql('CREATE INDEX IDX_88BDF3E9FE54D947 ON app_user (group_id)');
        foreach (['products', 'sales', 'inventory', 'groups', 'users', 'permissions'] as $module) {
            foreach (['view', 'create', 'update', 'delete'] as $action) {
                $this->addSql('INSERT INTO permission (module, action) VALUES (?, ?)', [$module, $action]);
            }
        }
    }

    public function down(Schema $schema): void
    {
        $this->addSql('ALTER TABLE group_permission DROP FOREIGN KEY FK_3784F318FE54D947');
        $this->addSql('ALTER TABLE group_permission DROP FOREIGN KEY FK_3784F318FED90CCA');
        $this->addSql('DROP TABLE permission');
        $this->addSql('DROP TABLE group_permission');
        $this->addSql('ALTER TABLE app_user DROP FOREIGN KEY FK_88BDF3E9FE54D947');
        $this->addSql('DROP INDEX IDX_88BDF3E9FE54D947 ON app_user');
        $this->addSql('ALTER TABLE app_user DROP group_id');
        $this->addSql('DROP TABLE user_group');
    }
}
