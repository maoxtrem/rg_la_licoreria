<?php

namespace App\EventListener;

use App\Authorization\Action;
use App\Authorization\Module;
use App\Authorization\PermissionChecker;
use App\Entity\User;
use Symfony\Bundle\SecurityBundle\Security;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\Event\ControllerEvent;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\KernelEvents;

/** Every route declaring _permission_module is protected before its controller runs. */
#[AsEventListener(event: KernelEvents::CONTROLLER, priority: 32)]
class ModulePermissionListener
{
    public function __construct(private readonly Security $security, private readonly PermissionChecker $permissions)
    {
    }

    public function __invoke(ControllerEvent $event): void
    {
        $request = $event->getRequest();
        $moduleName = $request->attributes->get('_permission_module');
        if ($moduleName === null) {
            // Only authentication/session endpoints are exempt from module grants.
            $sessionRoutes = ['api_csrf', 'api_login', 'api_logout', 'api_me', 'api_admin'];
            if (str_starts_with($request->getPathInfo(), '/api/') && !in_array($request->attributes->get('_route'), $sessionRoutes, true)) {
                throw new AccessDeniedHttpException();
            }
            return;
        }
        $module = is_string($moduleName) ? Module::tryFrom($moduleName) : null;
        $actionName = $request->attributes->get('_permission_action');
        $action = $actionName === null ? Action::forMethod($request->getMethod()) : (is_string($actionName) ? Action::tryFrom($actionName) : null);
        $user = $this->security->getUser();
        if (!$module || !$action || !$user instanceof User || !$this->permissions->allows($user, $module, $action)) {
            throw new AccessDeniedHttpException();
        }
    }
}
