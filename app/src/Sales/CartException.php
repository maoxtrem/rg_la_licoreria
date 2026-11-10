<?php

namespace App\Sales;

use Symfony\Component\HttpKernel\Exception\HttpException;

/** Public cart validation messages, safe to return through the JSON API. */
class CartException extends HttpException
{
}
