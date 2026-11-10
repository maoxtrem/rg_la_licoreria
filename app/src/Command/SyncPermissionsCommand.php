<?php

namespace App\Command;

use App\Authorization\Action;
use App\Authorization\Module;
use Doctrine\DBAL\Connection;
use Symfony\Component\Console\Attribute\AsCommand;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;

#[AsCommand(name: 'app:permissions:sync', description: 'Registra permisos de los módulos declarados sin modificar concesiones de grupos.')]
class SyncPermissionsCommand extends Command
{
    public function __construct(private readonly Connection $connection) { parent::__construct(); }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        $added = $this->connection->transactional(function (): int {
            $count = 0;
            foreach (Module::cases() as $module) {
                foreach (Action::cases() as $action) {
                    $count += $this->connection->executeStatement(
                        'INSERT INTO permission (module, action) VALUES (?, ?) ON DUPLICATE KEY UPDATE id = id', [$module->value, $action->value]
                    );
                }
            }
            return $count;
        });
        $output->writeln(sprintf('Catálogo sincronizado: %d permisos nuevos. Las asignaciones existentes se conservan.', $added));
        return Command::SUCCESS;
    }
}
