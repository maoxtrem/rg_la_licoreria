import { api } from './api.js';
import { alertError, alertPermission, notifySuccess, confirmDelete, showLoading, closeAlert } from './alerts.js';

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
    let barcodeFilter = '';
    const limit = 20;
    let loading = false;
    let busy = false;
    let editingId = null;
    let previewUrl = null;
    const formDialog = element('product-dialog');

    function loseAccess() {
        permissions = {};
        products = [];
        element('products-rows').replaceChildren();
        formDialog.close();
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
        element('products-empty-title').textContent = barcodeFilter ? 'Sin resultados.' : 'Tu catálogo empieza aquí.';
        element('products-empty-message').textContent = barcodeFilter
            ? 'No hay productos con ese código de barras. Revisa el código o limpia el filtro.'
            : permissions.create
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
            formDialog.close();
            void alertPermission('Tu grupo ya no tiene permiso para esta acción.');
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
            const imageCell = document.createElement('td');
            if (product.image_url) {
                const image = document.createElement('img');
                image.src = product.image_url;
                image.alt = product.name;
                image.className = 'product-thumbnail';
                image.loading = 'lazy';
                imageCell.append(image);
            } else {
                imageCell.textContent = 'Sin imagen';
                imageCell.className = 'muted small-text';
            }
            row.append(imageCell);
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
        for (const id of ['products-barcode-filter', 'products-filter-submit', 'products-filter-clear']) element(id).disabled = true;
        renderPagination();
        const listUrl = () => `/api/products?${new URLSearchParams({ page, limit, ...(barcodeFilter ? { barcode: barcodeFilter } : {}) })}`;
        try {
            if (!await refreshPermissions()) return;
            let result = await api(listUrl());
            if (redirectIfExpired(result.response)) return;
            if (result.response.status === 403) { loseAccess(); return; }
            if (!result.response.ok) throw new Error('No se pudo cargar el catálogo.');
            total = result.data.pagination.total;
            const lastPage = Math.max(1, Math.ceil(total / limit));
            if (page > lastPage) {
                page = lastPage;
                result = await api(listUrl());
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
            void alertError('No pudimos cargar los productos. Usa «Actualizar listado» para intentarlo nuevamente.');
        } finally {
            loading = false;
            element('products-loading').hidden = true;
            element('products-refresh').disabled = false;
            element('product-create').disabled = false;
            for (const id of ['products-barcode-filter', 'products-filter-submit', 'products-filter-clear']) element(id).disabled = false;
            renderPagination();
        }
    }

    function clearFormErrors() {
        for (const [input, error] of [...Object.values(fields), ['product-image', 'product-image-error']]) {
            element(input).removeAttribute('aria-invalid');
            element(error).hidden = true;
        }
    }

    function setBusy(value) {
        busy = value;
        element('product-fields').disabled = value;
        for (const id of ['product-save', 'product-cancel', 'product-close']) {
            element(id).disabled = value;
        }
        element('product-save').textContent = value ? 'Guardando…' : (editingId === null ? 'Crear producto' : 'Guardar cambios');
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
                    void alertError('Este producto ya no existe. El listado se ha actualizado.');
                    await loadProducts();
                    return;
                }
                if (!result.response.ok) throw new Error('No se pudo consultar el producto.');
                product = result.data.data;
            }
            if (action === 'delete') {
                if (await confirmDelete(product.name)) await deleteProduct(id);
                return;
            }
            editingId = id;
            element('product-form').reset();
            clearFormErrors();
            showImagePreview(product?.image_url);
            for (const [key, [input]] of Object.entries(fields)) element(input).value = product?.[key] ?? '';
            element('product-dialog-title').textContent = id === null ? 'Nuevo producto' : 'Editar producto';
            setBusy(false);
            formDialog.showModal();
            element('product-name').focus();
        } catch {
            void alertError('No pudimos abrir el producto. Inténtalo nuevamente.');
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
            headers: { ...(data instanceof FormData ? {} : { 'Content-Type': 'application/json' }), 'X-CSRF-Token': csrf.data.products },
            ...(data === undefined ? {} : { body: data instanceof FormData ? data : JSON.stringify(data) }),
        });
    }

    async function handleFailure(result, showFieldErrors = false) {
        if (!result || redirectIfExpired(result.response)) return true;
        if (result.response.ok) return false;
        if (result.response.status === 403) {
            formDialog.close();
            if (await refreshPermissions()) await alertPermission('La acción no está autorizada. Revisa los permisos de tu grupo.');
        } else if (result.response.status === 404) {
            formDialog.close();
            await alertError('El producto ya no existe.');
            await loadProducts();
        } else {
            let first = null;
            if (showFieldErrors) {
                for (const [key, text] of Object.entries(result.data?.errors ?? {})) {
                    const field = key === 'image' ? ['product-image', 'product-image-error'] : fields[key];
                    if (!field) continue;
                    const [input, error] = field;
                    element(input).setAttribute('aria-invalid', 'true');
                    element(error).textContent = text;
                    element(error).hidden = false;
                    first ??= element(input);
                }
            }
            await alertError(result.data?.error ?? 'No se pudo completar la solicitud.');
            if (first) setTimeout(() => first.focus(), 0);
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
            const image = element('product-image').files[0];
            let payload = data;
            if (image) {
                payload = new FormData();
                payload.append('data', JSON.stringify(data));
                payload.append('image', image);
            }
            const result = await write(editingId === null ? '/api/products' : `/api/products/${editingId}`, editingId === null || image ? 'POST' : 'PUT', payload);
            if (await handleFailure(result, true)) return;
            formDialog.close();
            void notifySuccess(editingId === null ? 'Producto creado correctamente.' : 'Cambios guardados correctamente.');
            if (editingId === null) page = 1;
            await loadProducts();
        } catch {
            void alertError('No pudimos confirmar la operación. Inténtalo de nuevo o actualiza el listado para comprobar el resultado.');
        } finally {
            setBusy(false);
        }
    });

    async function deleteProduct(id) {
        setBusy(true);
        try {
            if (!await refreshPermissions('delete')) return;
            void showLoading('Eliminando producto…');
            const result = await write(`/api/products/${id}`, 'DELETE');
            closeAlert();
            if (await handleFailure(result)) return;
            void notifySuccess('Producto eliminado correctamente.');
            await loadProducts();
        } catch {
            closeAlert();
            void alertError('No pudimos confirmar la eliminación. Actualiza el listado para comprobar el resultado.');
        } finally {
            setBusy(false);
        }
    }

    function showImagePreview(url) {
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = null;
        const preview = element('product-image-preview');
        preview.hidden = !url;
        if (url) preview.src = url;
        else preview.removeAttribute('src');
    }

    element('product-image').addEventListener('change', () => {
        const file = element('product-image').files[0];
        showImagePreview(null);
        element('product-image').removeAttribute('aria-invalid');
        element('product-image-error').hidden = true;
        if (!file) return;
        if (file.size > 2 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
            element('product-image').value = '';
            element('product-image').setAttribute('aria-invalid', 'true');
            element('product-image-error').textContent = 'Selecciona una imagen JPG, PNG o WebP de hasta 2 MB.';
            element('product-image-error').hidden = false;
            return;
        }
        previewUrl = URL.createObjectURL(file);
        element('product-image-preview').src = previewUrl;
        element('product-image-preview').hidden = false;
    });
    formDialog.addEventListener('close', () => showImagePreview(null));

    function filterProducts(value) {
        if (busy || loading) return;
        barcodeFilter = value.trim();
        element('products-barcode-filter').value = barcodeFilter;
        page = 1;
        void loadProducts();
    }

    element('products-filter-form').addEventListener('submit', (event) => {
        event.preventDefault();
        filterProducts(element('products-barcode-filter').value);
    });
    element('products-filter-clear').addEventListener('click', () => filterProducts(''));
    element('product-create').addEventListener('click', () => openProduct());
    for (const id of ['product-close', 'product-cancel']) element(id).addEventListener('click', () => { if (!busy) formDialog.close(); });
    for (const dialog of [formDialog]) dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
    element('products-refresh').addEventListener('click', () => { if (busy) return; loadProducts(); });
    element('products-previous').addEventListener('click', () => { if (!busy && !loading && page > 1) { page--; loadProducts(); } });
    element('products-next').addEventListener('click', () => { if (!busy && !loading && page * limit < total) { page++; loadProducts(); } });
    applyPermissions();
    await loadProducts();
}
