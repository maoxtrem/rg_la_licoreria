<?php

namespace App\Command;

use App\Entity\User;
use App\Repository\UserRepository;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Component\Console\Attribute\AsCommand;
use Symfony\Component\Console\Command\Command;
use Symfony\Component\Console\Input\InputInterface;
use Symfony\Component\Console\Output\OutputInterface;
use Symfony\Component\PasswordHasher\Hasher\UserPasswordHasherInterface;

#[AsCommand(name: 'app:create-admin', description: 'Crea el administrador inicial admin sin modificar usuarios existentes.')]
class CreateAdminCommand extends Command
{
    public function __construct(
        private readonly UserRepository $users,
        private readonly EntityManagerInterface $entityManager,
        private readonly UserPasswordHasherInterface $passwordHasher,
    ) {
        parent::__construct();
    }

    protected function execute(InputInterface $input, OutputInterface $output): int
    {
        if ($this->users->findOneBy(['username' => 'admin'])) {
            $output->writeln('El usuario admin ya existe; no se modificó.');

            return Command::SUCCESS;
        }

        $user = new User('admin', [User::ROLE_ADMIN]);
        $user->setPassword($this->passwordHasher->hashPassword($user, 'admin'));
        $this->entityManager->persist($user);
        $this->entityManager->flush();
        $output->writeln('Administrador inicial creado: admin.');

        return Command::SUCCESS;
    }
}
