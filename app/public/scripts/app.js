import { api } from './api.js';
import { alertError } from './alerts.js';
import { startProducts } from './products.js';
import { startSales } from './sales.js';
import { startCompany } from './company.js';
import { startBilling } from './billing.js';
import { startInventory } from './inventory.js';

const element = (id) => document.getElementById(id);
const modules = {
    '/productos': { key: 'products', title: 'Productos', group: 'Operativos', description: 'Aquí encontrarás tu catálogo de productos.', ready: true },
    '/ventas': { key: 'sales', title: 'Ventas', group: 'Operativos', description: 'Aquí podrás gestionar las ventas de tu negocio.', ready: true },
    '/facturacion': { key: 'billing', title: 'Facturación', group: 'Operativos', description: 'Aquí podrás gestionar la facturación de tu negocio.', ready: true },
    '/inventario': { key: 'inventory', title: 'Inventario', group: 'Operativos', description: 'Aquí podrás consultar y gestionar tus existencias.', ready: true },
    '/contabilidad': { key: 'accounting', title: 'Contabilidad', group: 'Operativos', description: 'Aquí podrás consultar y gestionar la contabilidad de tu negocio.', permissioned: false },
    '/empresa': { key: 'company', title: 'Empresa', group: 'Administrativos', description: 'Datos de la empresa para las facturas.', ready: true },
    '/grupos': { key: 'groups', title: 'Grupos', group: 'Administrativos', description: 'Aquí podrás organizar los grupos de trabajo.', ready: false },
    '/usuarios': { key: 'users', title: 'Usuarios', group: 'Administrativos', description: 'Aquí podrás gestionar las cuentas del sistema.', ready: false },
    '/permisos': { key: 'permissions', title: 'Permisos', group: 'Administrativos', description: 'Aquí podrás administrar los permisos de acceso.', ready: false },
};

function showView(id) {
    element('loading').hidden = true;
    element(id).hidden = false;
}

function renderHomeModules() {
    const container = element('home-modules');
    container.replaceChildren();
    for (const group of ['Operativos', 'Administrativos']) {
        const heading = document.createElement('h2'); heading.className = 'module-cards-heading'; heading.textContent = group;
        const grid = document.createElement('div'); grid.className = 'module-cards-grid';
        Object.entries(modules).filter(([, module]) => module.group === group).forEach(([path, module]) => {
            const card = document.createElement(module.ready ? 'a' : 'article');
            card.className = 'module-card home-module-card' + (module.ready ? '' : ' module-card-pending');
            if (module.ready) card.href = path;
            const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = module.ready ? 'Disponible' : 'Próximamente';
            const title = document.createElement('h3'); title.textContent = module.title;
            const description = document.createElement('p'); description.className = 'muted'; description.textContent = module.description;
            card.append(badge, title, description);
            grid.append(card);
        });
        container.append(heading, grid);
    }
}

async function initialize() {
    try {
        const { response, data } = await api('/api/me');
        if (response.status === 401) {
            if (location.pathname !== '/login') {
                location.replace('/login');
                return;
            }
            document.title = 'Iniciar sesión · La Licorería';
            showView('login-view');
            element('username').focus();
            return;
        }
        if (!response.ok) throw new Error('No se pudo consultar la sesión.');
        if (location.pathname === '/login') {
            location.replace('/');
            return;
        }

        element('logout-button').hidden = false;
        document.querySelectorAll('[data-username]').forEach((node) => {
            node.textContent = data.user.username;
        });
        const isAdmin = data.user.roles.includes('ROLE_ADMIN');
        element('role-label').textContent = isAdmin ? 'Administrador' : 'Usuario';
        element('admin-link').hidden = !isAdmin;

        element('workspace').hidden = false;
        document.querySelectorAll('[data-nav]').forEach((link) => {
            const path = link.getAttribute('href');
            const section = modules[path];
            link.hidden = section && section.permissioned !== false ? !data.user.permissions?.[section.key]?.view : false;
            if (path === location.pathname) link.setAttribute('aria-current', 'page');
        });

        for (const id of ['admin-navigation', 'operational-navigation']) {
            element(id).hidden = ![...element(id).querySelectorAll('[data-nav]')].some((link) => !link.hidden);
        }

        const module = modules[location.pathname];
        if (module) {
            element('module-group').textContent = module.group;
            element('module-title').textContent = module.title;
            element('module-description').textContent = module.description;
            document.title = `${module.title} · La Licorería`;
            const access = module.permissioned === false ? { data: { actions: {} } } : await api(`/api/modules/${module.key}/access`);
            if (module.permissioned !== false) {
                if (access.response.status === 401) {
                    location.replace('/login');
                    return;
                }
                if (access.response.status === 403) {
                    showView('access-denied-view');
                    return;
                }
                if (!access.response.ok) throw new Error('No se pudo consultar el acceso.');
            }
            if (module.key === 'products' || module.key === 'sales' || module.key === 'company' || module.key === 'billing' || module.key === 'inventory') {
                const view = `${module.key}-view`;
                showView(view);
                const start = { products: startProducts, sales: startSales, company: startCompany, billing: startBilling, inventory: startInventory }[module.key];
                await start({
                    actions: access.data.actions,
                    onAccessLost: () => {
                        element(view).hidden = true;
                        const link = document.querySelector(`[data-nav][href="${location.pathname}"]`);
                        if (link) link.hidden = true;
                        for (const id of ['operational-navigation', 'admin-navigation']) {
                            element(id).hidden = ![...element(id).querySelectorAll('[data-nav]')].some((item) => !item.hidden);
                        }
                        showView('access-denied-view');
                    },
                });
            } else {
                showView('module-view');
            }
            return;
        }

        if (location.pathname === '/admin') {
            const admin = await api('/api/admin');
            if (admin.response.status === 401) {
                location.replace('/login');
                return;
            }
            if (admin.response.status === 403) { showView('access-denied-view'); return; }
            if (!admin.response.ok) throw new Error('No se pudo consultar la administración.');
            element('admin-message').textContent = admin.data.message ?? admin.data.error;
            document.title = 'Administración · La Licorería';
            renderHomeModules();
            showView('admin-view');
        } else {
            document.title = 'Inicio · La Licorería';
            showView('home-view');
        }
    } catch {
        element('loading').hidden = true;
        element('connection-error').hidden = false;
        await alertError('No pudimos conectar con el servidor. Recarga la página para intentarlo nuevamente.');
    }
}

element('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = element('login-button');
    button.disabled = true;
    try {
        const csrf = await api('/api/csrf');
        if (!csrf.response.ok) throw new Error('No se pudo preparar el acceso.');
        const { response, data } = await api('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: element('username').value,
                password: element('password').value,
                _csrf_token: csrf.data.login,
            }),
        });
        if (!response.ok) {
            await alertError( data.error ?? 'No se pudo iniciar sesión.');
            element('password').value = '';
            element('password').focus();
            return;
        }
        location.assign('/');
    } catch {
        await alertError( 'No pudimos conectar con el servidor. Inténtalo nuevamente.');
    } finally {
        button.disabled = false;
    }
});

element('logout-button').addEventListener('click', async () => {
    const button = element('logout-button');
    button.disabled = true;
    try {
        const csrf = await api('/api/csrf');
        if (!csrf.response.ok) throw new Error('No se pudo preparar el cierre de sesión.');
        const { response } = await api('/api/logout', {
            method: 'POST',
            body: new URLSearchParams({ _csrf_token: csrf.data.logout }),
        });
        if (!response.ok) throw new Error('No se pudo cerrar la sesión.');
        location.replace('/login');
    } catch {
        await alertError( 'No pudimos cerrar la sesión. Inténtalo nuevamente.');
        button.disabled = false;
    }
});

initialize();
