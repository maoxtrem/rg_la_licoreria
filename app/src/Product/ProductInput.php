<?php

namespace App\Product;

/** Validates API input without converting monetary values to floating point. */
final class ProductInput
{
    public const FIELDS = ['name', 'barcode', 'sale_price', 'cost_price'];

    /** @return array{values: array<string, string>, errors: array<string, string>} */
    public function validate(array $data, bool $partial = false): array
    {
        $values = [];
        $errors = [];
        foreach (array_diff(array_keys($data), self::FIELDS) as $field) {
            $errors[$field] = 'Campo no permitido.';
        }
        foreach (self::FIELDS as $field) {
            if (!array_key_exists($field, $data)) {
                if (!$partial) $errors[$field] = 'Este campo es obligatorio.';
                continue;
            }
            $value = $data[$field];
            if (in_array($field, ['sale_price', 'cost_price'], true)) {
                if ((!is_string($value) && !is_int($value))
                    || !preg_match('/^\d{1,10}(?:\.\d{1,2})?$/D', (string) $value)) {
                    $errors[$field] = 'Usa un importe no negativo de hasta 10 enteros y 2 decimales, como texto: "12500.00".';
                    continue;
                }
                $parts = explode('.', (string) $value);
                $values[$field] = (ltrim($parts[0], '0') ?: '0').'.'.str_pad($parts[1] ?? '', 2, '0');
                continue;
            }
            $limit = $field === 'name' ? 180 : 100;
            if (!is_string($value) || trim($value) === '' || mb_strlen(trim($value)) > $limit) {
                $errors[$field] = "Debe ser un texto de entre 1 y $limit caracteres.";
                continue;
            }
            $values[$field] = trim($value);
        }
        if ($partial && $data === []) {
            $errors['_request'] = 'Incluye al menos un campo para actualizar.';
        }

        return ['values' => $values, 'errors' => $errors];
    }
}
