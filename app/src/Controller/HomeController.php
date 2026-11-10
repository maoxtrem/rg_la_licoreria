<?php

namespace App\Controller;

use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

class HomeController extends AbstractController
{
    #[Route('/', name: 'app_home', methods: ['GET'])]
    #[Route('/login', name: 'app_login', methods: ['GET'])]
    #[Route('/admin', name: 'app_admin', methods: ['GET'])]
    #[Route('/{section}', name: 'app_module', requirements: ['section' => 'productos|ventas|facturacion|empresa|inventario|grupos|usuarios|permisos'], methods: ['GET'])]
    public function index(): Response
    {
        return $this->render('app/index.html.twig');
    }
}
