import { api } from './api.js';

const element = (id) => document.getElementById(id);
const fields = {
    name: ['product-name', 'product-name-error'],
    barcode: ['product-barcode', 'product-barcode-error'],
    sale_price: ['product-sale-price', 'product-sale-price-error'],
    cost_price: ['product-cost-price', 'product-cost-price-error'],
};
const number = new Intl.NumberFormat('es-CO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export async function startProducts({ actions, onAccessLost }) {
    let permissions = actions;
    let products = [];
    let page = 1;
    let total = 0;
    const limit = 20;
    let loading = false;
    let busy = false;
    let editingId = null;
    let deletingId = null;
    const formDialog = element('product-dialog');
    const deleteDialog = element('product-delete-dialog');

    function message(id, text, error = true) {
        const node = element(id);
        node.textContent = text;
        node.hidden = false;
        if (id === 'products-feedback') node.classList.toggle('notice-error', error);
    }

    function loseAccess() {
        permissions = {};
        products = [];
        element('products-rows').replaceChildren();
        formDialog.close();
        deleteDialog.close();
        onAccessLost();
    }

    function redirectIfExpired(response) {
        if (response.status !== 401) return false;
        location.replace('/login');
        return true;
    }

    function applyPermissions() {
        element('product-create').hidden = !permissions.create;
        element('products-readonly').hidden = permissions.create || permissions.update || permissions.delete;
        element('products-actions-heading').hidden = !permissions.update && !permissions.delete;
        element('products-empty-message').textContent = permissions.create
            ? 'Añade tu primer producto para comenzar a organizar el catálogo.'
            : 'Todavía no hay productos registrados.';
        renderRows();
    }

    async function refreshPermissions(action = 'view') {
        const { response, data } = await api('/api/modules/products/access');
        if (redirectIfExpired(response)) return false;
        if (response.status === 403) {
            loseAccess();
            return false;
        }
        if (!response.ok) throw new Error('No se pudieron consultar los permisos.');
        permissions = data.actions;
        applyPermissions();
        if (!permissions[action]) {
            message('products-feedback', 'Tu grupo ya no tiene permiso para esta acción.');
            return false;
        }
        return true;
    }

    function actionButton(label, action, product) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = action === 'delete' ? 'table-action table-action-danger' : 'table-action';
        button.textContent = label;
        button.setAttribute('aria-label', `${label} ${product.name}`);
        button.addEventListener('click', () => openProduct(product.id, action));
        return button;
    }

    function renderRows() {
        const rows = products.map((product) => {
            const row = document.createElement('tr');
            for (const [value, className] of [
                [product.name, 'product-name-cell'], [product.barcode, 'barcode-cell'],
                [number.format(Number(product.sale_price)), 'price-cell'],
                [number.format(Number(product.cost_price)), 'price-cell'],
            ]) {
                const cell = document.createElement('td');
                cell.textContent = value;
                cell.className = className;
                row.append(cell);
            }
            if (permissions.update || permissions.delete) {
                const cell = document.createElement('td');
                cell.className = 'row-actions';
                if (permissions.update) cell.append(actionButton('Editar', 'update', product));
                if (permissions.delete) cell.append(actionButton('Eliminar', 'delete', product));
                row.append(cell);
            }
            return row;
        });
        element('products-rows').replaceChildren(...rows);
    }

    function renderPagination() {
        const pages = Math.max(1, Math.ceil(total / limit));
        element('products-count').textContent = String(total);
        element('products-pagination').hidden = total === 0;
        element('products-range').textContent = `${(page - 1) * limit + 1}–${Math.min(page * limit, total)} de ${total} productos`;
        element('products-page-number').textContent = `${page} de ${pages}`;
        element('products-previous').disabled = loading || page <= 1;
        element('products-next').disabled = loading || page >= pages;
    }

    async function loadProducts() {
        if (loading) return;
        loading = true;
        element('products-loading').hidden = false;
        element('products-table-container').hidden = true;
        element('products-empty').hidden = true;
        element('products-refresh').disabled = true;
        element('product-create').disabled = true;
        renderPagination();
        try {
            if (!await refreshPermissions()) return;
            let result = await api(`/api/products?page=${page}&limit=${limit}`);
            if (redirectIfExpired(result.response)) return;
            if (result.response.status === 403) { loseAccess(); return; }
            if (!result.response.ok) throw new Error('No se pudo cargar el catálogo.');
            total = result.data.pagination.total;
            const lastPage = Math.max(1, Math.ceil(total / limit));
            if (page > lastPage) {
                page = lastPage;
                result = await api(`/api/products?page=${page}&limit=${limit}`);
                if (redirectIfExpired(result.response)) return;
                if (result.response.status === 403) { loseAccess(); return; }
                if (!result.response.ok) throw new Error('No se pudo cargar el catálogo.');
                total = result.data.pagination.total;
            }
            products = result.data.data;
            renderRows();
            element('products-table-container').hidden = products.length === 0;
            element('products-empty').hidden = products.length !== 0;
        } catch {
            message('products-feedback', 'No pudimos cargar los productos. Usa «Actualizar listado» para intentarlo nuevamente.');
        } finally {
            loading = false;
            element('products-loading').hidden = true;
            element('products-refresh').disabled = false;
            element('product-create').disabled = false;
            renderPagination();
        }
    }

    function clearFormErrors() {
        element('product-form-error').hidden = true;
        for (const [input, error] of Object.values(fields)) {
            element(input).removeAttribute('aria-invalid');
            element(error).hidden = true;
        }
    }

    function setBusy(value) {
        busy = value;
        element('product-fields').disabled = value;
        for (const id of ['product-save', 'product-cancel', 'product-close', 'product-delete-confirm', 'product-delete-cancel']) {
            element(id).disabled = value;
        }
        element('product-save').textContent = value ? 'Guardando…' : (editingId === null ? 'Crear producto' : 'Guardar cambios');
        element('product-delete-confirm').textContent = value ? 'Eliminando…' : 'Eliminar producto';
    }

    async function openProduct(id = null, action = 'create') {
        if (busy || loading) return;
        setBusy(true);
        try {
            if (!await refreshPermissions(action)) return;
            let product = null;
            if (id !== null) {
                const result = await api(`/api/products/${id}`);
                if (redirectIfExpired(result.response)) return;
                if (result.response.status === 403) { loseAccess(); return; }
                if (result.response.status === 404) {
                    message('products-feedback', 'Este producto ya no existe. El listado se ha actualizado.');
                    await loadProducts();
                    return;
                }
                if (!result.response.ok) throw new Error('No se pudo consultar el producto.');
                product = result.data.data;
            }
            if (action === 'delete') {
                deletingId = id;
                element('product-delete-name').textContent = product.name;
                element('product-delete-error').hidden = true;
                setBusy(false);
                deleteDialog.showModal();
                element('product-delete-cancel').focus();
                return;
            }
            editingId = id;
            element('product-form').reset();
            clearFormErrors();
            for (const [key, [input]] of Object.entries(fields)) element(input).value = product?.[key] ?? '';
            element('product-dialog-title').textContent = id === null ? 'Nuevo producto' : 'Editar producto';
            setBusy(false);
            formDialog.showModal();
            element('product-name').focus();
        } catch {
            message('products-feedback', 'No pudimos abrir el producto. Inténtalo nuevamente.');
        } finally {
            setBusy(false);
        }
    }

    async function write(path, method, data) {
        const csrf = await api('/api/csrf');
        if (redirectIfExpired(csrf.response)) return null;
        if (!csrf.response.ok) throw new Error('No se pudo preparar la solicitud.');
        return api(path, {
            method,
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.data.products },
            ...(data === undefined ? {} : { body: JSON.stringify(data) }),
        });
    }

    async function handleFailure(result, errorId) {
        if (!result || redirectIfExpired(result.response)) return true;
        if (result.response.ok) return false;
        if (result.response.status === 403) {
            formDialog.close();
            deleteDialog.close();
            if (await refreshPermissions()) message('products-feedback', 'La acción no está autorizada. Revisa los permisos de tu grupo o inténtalo nuevamente.');
        } else if (result.response.status === 404) {
            formDialog.close();
            deleteDialog.close();
            message('products-feedback', 'El producto ya no existe.');
            await loadProducts();
        } else {
            message(errorId, result.data?.error ?? 'No se pudo completar la solicitud.');
            if (errorId === 'product-form-error') {
                let first = null;
                for (const [key, text] of Object.entries(result.data?.errors ?? {})) {
                    if (!fields[key]) continue;
                    const [input, error] = fields[key];
                    element(input).setAttribute('aria-invalid', 'true');
                    message(error, text);
                    first ??= element(input);
                }
                // The fieldset is re-enabled in finally before moving focus.
                if (first) setTimeout(() => first.focus(), 0);
            }
        }
        return true;
    }

    element('product-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy) return;
        clearFormErrors();
        setBusy(true);
        const action = editingId === null ? 'create' : 'update';
        try {
            if (!await refreshPermissions(action)) { formDialog.close(); return; }
            const data = Object.fromEntries(Object.entries(fields).map(([key, [input]]) => [
                key, key.endsWith('_price') ? element(input).value.trim().replace(',', '.') : element(input).value.trim(),
            ]));
            const result = await write(editingId === null ? '/api/products' : `/api/products/${editingId}`, editingId === null ? 'POST' : 'PUT', data);
            if (await handleFailure(result, 'product-form-error')) return;
            formDialog.close();
            message('products-feedback', editingId === null ? 'Producto creado correctamente.' : 'Cambios guardados correctamente.', false);
            if (editingId === null) page = 1;
            await loadProducts();
        } catch {
            message('product-form-error', 'No pudimos confirmar la operación. Inténtalo de nuevo o actualiza el listado para comprobar el resultado.');
        } finally {
            setBusy(false);
        }
    });

    element('product-delete-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy || deletingId === null) return;
        setBusy(true);
        element('product-delete-error').hidden = true;
        try {
            if (!await refreshPermissions('delete')) { deleteDialog.close(); return; }
            const result = await write(`/api/products/${deletingId}`, 'DELETE');
            if (await handleFailure(result, 'product-delete-error')) return;
            deleteDialog.close();
            message('products-feedback', 'Producto eliminado correctamente.', false);
            await loadProducts();
        } catch {
            message('product-delete-error', 'No pudimos confirmar la eliminación. Actualiza el listado para comprobar el resultado.');
        } finally {
            setBusy(false);
        }
    });

    element('product-create').addEventListener('click', () => openProduct());
    for (const id of ['product-close', 'product-cancel']) element(id).addEventListener('click', () => { if (!busy) formDialog.close(); });
    element('product-delete-cancel').addEventListener('click', () => { if (!busy) deleteDialog.close(); });
    for (const dialog of [formDialog, deleteDialog]) dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
    element('products-refresh').addEventListener('click', () => { if (busy) return; element('products-feedback').hidden = true; loadProducts(); });
    element('products-previous').addEventListener('click', () => { if (!busy && !loading && page > 1) { page--; loadProducts(); } });
    element('products-next').addEventListener('click', () => { if (!busy && !loading && page * limit < total) { page++; loadProducts(); } });
    applyPermissions();
    await loadProducts();
}
