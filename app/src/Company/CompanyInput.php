<?php

namespace App\Company;

final class CompanyInput
{
    public const LIMITS = ['name' => 180, 'address' => 255, 'phone' => 40, 'nit' => 40];

    public function validate(array $data, bool $partial = false): array
    {
        $values = [];
        $errors = [];
        foreach (array_diff(array_keys($data), array_keys(self::LIMITS)) as $field) {
            $errors[$field] = 'Campo no permitido.';
        }
        foreach (self::LIMITS as $field => $limit) {
            if (!array_key_exists($field, $data)) {
                if (!$partial) $errors[$field] = 'Este campo es obligatorio.';
                continue;
            }
            $value = $data[$field];
            if (!is_string($value) || trim($value) === '' || mb_strlen(trim($value)) > $limit
                || preg_match('/[\x00-\x1f\x7f]/u', $value)) {
                $errors[$field] = "Usa un texto de entre 1 y $limit caracteres, sin saltos de línea ni caracteres de control.";
                continue;
            }
            $values[$field] = trim($value);
        }
        if ($partial && $data === []) $errors['_request'] = 'Incluye al menos un campo para actualizar.';
        return ['values' => $values, 'errors' => $errors];
    }
}
