<?php

namespace App\Storage;

use Aws\S3\S3Client;
use Aws\S3\Exception\S3Exception;
use Symfony\Component\DependencyInjection\Attribute\Autowire;
use Symfony\Component\HttpFoundation\File\UploadedFile;

final class ProductImages
{
    private S3Client $client;

    public function __construct(
        #[Autowire('%env(MINIO_ENDPOINT)%')] string $endpoint,
        #[Autowire('%env(MINIO_REGION)%')] string $region,
        #[Autowire('%env(MINIO_ROOT_USER)%')] string $user,
        #[Autowire('%env(MINIO_ROOT_PASSWORD)%')] string $password,
        #[Autowire('%env(MINIO_BUCKET)%')] private readonly string $bucket,
    ) {
        $this->client = new S3Client([
            'version' => 'latest', 'region' => $region, 'endpoint' => $endpoint,
            'use_path_style_endpoint' => true,
            'credentials' => ['key' => $user, 'secret' => $password],
            'http' => ['connect_timeout' => 3, 'timeout' => 15],
        ]);
    }

    public function invalid(UploadedFile $file): bool
    {
        if (!$file->isValid() || $file->getSize() > 2 * 1024 * 1024) return true;
        $info = @getimagesize($file->getPathname());
        return !$info || !in_array($info['mime'], ['image/jpeg', 'image/png', 'image/webp'], true)
            || $info['mime'] !== (new \finfo(FILEINFO_MIME_TYPE))->file($file->getPathname()) || $info[0] * $info[1] > 20000000;
    }

    public function upload(UploadedFile $file): string
    {
        try {
            $this->client->headBucket(['Bucket' => $this->bucket]);
        } catch (S3Exception $exception) {
            if ($exception->getStatusCode() !== 404) throw $exception;
            try {
                $this->client->createBucket(['Bucket' => $this->bucket]);
            } catch (S3Exception $creation) {
                if ($creation->getAwsErrorCode() !== 'BucketAlreadyOwnedByYou') throw $creation;
            }
        }
        $type = (new \finfo(FILEINFO_MIME_TYPE))->file($file->getPathname());
        $extension = ['image/jpeg' => 'jpg', 'image/png' => 'png', 'image/webp' => 'webp'][$type];
        $key = 'products/'.bin2hex(random_bytes(20)).'.'.$extension;
        $this->client->putObject([
            'Bucket' => $this->bucket, 'Key' => $key,
            'SourceFile' => $file->getPathname(), 'ContentType' => $type,
        ]);
        return $key;
    }

    public function read(string $key): array
    {
        $result = $this->client->getObject(['Bucket' => $this->bucket, 'Key' => $key]);
        return ['body' => (string) $result['Body'], 'type' => $result['ContentType']];
    }

    public function delete(string $key): void
    {
        try {
            $this->client->deleteObject(['Bucket' => $this->bucket, 'Key' => $key]);
        } catch (\Throwable) {
            error_log('No se pudo eliminar de MinIO la imagen de producto: '.$key);
        }
    }
}
