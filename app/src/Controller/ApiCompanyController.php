<?php

namespace App\Controller;

use App\Company\CompanyInput;
use App\Entity\Company;
use App\Http\ApiInput;
use Doctrine\DBAL\Exception\UniqueConstraintViolationException;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\Routing\Attribute\Route;
use Symfony\Component\Security\Http\Attribute\IsGranted;

#[Route('/api/company', defaults: ['_format' => 'json', '_permission_module' => 'company'])]
#[IsGranted('ROLE_USER')]
class ApiCompanyController extends AbstractController
{
    public function __construct(
        private readonly EntityManagerInterface $entityManager,
        private readonly CompanyInput $validator,
        private readonly ApiInput $input,
    ) {}

    #[Route('', name: 'api_company_show', methods: ['GET'])]
    public function show(): JsonResponse
    {
        $company = $this->entityManager->find(Company::class, 1);
        return $this->json(['data' => $company?->toArray()], headers: ['Cache-Control' => 'no-store']);
    }

    #[Route('', name: 'api_company_create', methods: ['POST'])]
    public function create(Request $request): JsonResponse
    {
        $result = $this->validator->validate($this->input->read($request, 'company'));
        if ($result['errors']) return $this->invalid($result['errors']);
        if ($this->entityManager->find(Company::class, 1)) return $this->conflict();
        $company = new Company($result['values']);
        $this->entityManager->persist($company);
        try {
            $this->entityManager->flush();
        } catch (UniqueConstraintViolationException) {
            return $this->conflict();
        }
        return $this->json(['data' => $company->toArray()], 201, [
            'Location' => $this->generateUrl('api_company_show'), 'Cache-Control' => 'no-store',
        ]);
    }

    #[Route('', name: 'api_company_update', methods: ['PUT', 'PATCH'])]
    public function update(Request $request): JsonResponse
    {
        $data = $this->input->read($request, 'company');
        $company = $this->entityManager->find(Company::class, 1) ?? throw $this->createNotFoundException();
        $result = $this->validator->validate($data, $request->isMethod('PATCH'));
        if ($result['errors']) return $this->invalid($result['errors']);
        $company->update($result['values'] + $company->toArray());
        $this->entityManager->flush();
        return $this->json(['data' => $company->toArray()], headers: ['Cache-Control' => 'no-store']);
    }

    private function invalid(array $errors): JsonResponse
    {
        return $this->json(['error' => 'Revisa los datos de la empresa.', 'errors' => $errors], 422);
    }

    private function conflict(): JsonResponse
    {
        return $this->json(['error' => 'La empresa ya está registrada. Edita sus datos.'], 409);
    }
}
