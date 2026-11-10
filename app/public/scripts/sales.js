import { api } from './api.js';
import { alertError, alertPermission, confirmCartClear, confirmInvoicePayment, notifySuccess } from './alerts.js';

const element = (id) => document.getElementById(id);
// Formatting only: avoid floating point even for unusually large cart totals.
const money = (value) => {
    const [whole, fraction = '00'] = value.split('.');
    return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')}`;
};

export async function startSales({ actions, onAccessLost }) {
    let permissions = actions;
    let cart = { items: [], line_count: 0, quantity: 0, total: '0.00' };
    let chain = Promise.resolve();
    let pending = 0;
    let ready = false;
    let lost = false;
    const input = element('sales-barcode');

    function focusScanner() {
        if (lost || !permissions.create || !ready || document.querySelector('.swal2-container')) return;
        input.focus();
    }

    function state() {
        input.disabled = !ready || !permissions.create || lost;
        element('sales-scan-button').disabled = input.disabled;
        element('sales-refresh').disabled = pending > 0;
        for (const id of ['sales-pay', 'sales-pending']) {
            element(id).hidden = !permissions.create;
            element(id).disabled = !ready || lost || pending > 0 || !cart.items.length;
        }
        element('sales-clear').hidden = !permissions.delete;
        element('sales-clear').disabled = pending > 0 || cart.items.length === 0;
        element('sales-readonly').hidden = permissions.create;
        for (const control of element('sales-rows').querySelectorAll('button, input')) {
            control.disabled = pending > 0 || (control.dataset.minimum === 'true');
        }
        if (pending > 0) element('sales-scan-status').textContent = `Procesando ${pending} ${pending === 1 ? 'operación' : 'operaciones'}…`;
    }

    function render() {
        const rows = cart.items.map((item) => {
            const row = document.createElement('tr');
            row.dataset.productId = String(item.product_id);
            const product = document.createElement('td');
            product.className = 'product-name-cell';
            const name = document.createElement('strong');
            name.textContent = item.name;
            const code = document.createElement('span');
            code.className = 'cart-barcode';
            code.textContent = item.barcode;
            product.append(name, code);
            const price = document.createElement('td');
            price.className = 'price-cell';
            price.textContent = money(item.unit_price);
            const quantity = document.createElement('td');
            if (permissions.update) {
                const controls = document.createElement('div');
                controls.className = 'quantity-controls';
                for (const [text, delta] of [['−', -1], ['+', 1]]) {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.textContent = text;
                    button.className = 'quantity-button';
                    button.setAttribute('aria-label', `${delta < 0 ? 'Restar' : 'Sumar'} unidad de ${item.name}`);
                    if ((delta < 0 && item.quantity === 1) || (delta > 0 && item.quantity === 9999)) button.dataset.minimum = 'true';
                    button.addEventListener('click', () => changeQuantity(item.product_id, item.quantity + delta));
                    controls.append(button);
                }
                const field = document.createElement('input');
                field.type = 'number'; field.min = '1'; field.max = '9999'; field.step = '1';
                field.value = String(item.quantity);
                field.setAttribute('aria-label', `Cantidad de ${item.name}`);
                field.addEventListener('change', () => changeQuantity(item.product_id, Number(field.value)));
                controls.insertBefore(field, controls.lastChild);
                quantity.append(controls);
            } else {
                quantity.textContent = String(item.quantity);
                quantity.className = 'cart-quantity';
            }
            const subtotal = document.createElement('td');
            subtotal.className = 'price-cell';
            subtotal.textContent = money(item.subtotal);
            row.append(product, price, quantity, subtotal);
            if (permissions.delete) {
                const cell = document.createElement('td');
                cell.className = 'row-actions';
                const button = document.createElement('button');
                button.className = 'table-action table-action-danger'; button.type = 'button';
                button.textContent = 'Retirar';
                button.setAttribute('aria-label', `Retirar ${item.name}`);
                button.addEventListener('click', () => enqueue(() => mutate('delete', `/api/sales/cart/items/${item.product_id}`, 'DELETE')));
                cell.append(button); row.append(cell);
            }
            return row;
        });
        element('sales-rows').replaceChildren(...rows);
        element('sales-table-container').hidden = rows.length === 0;
        element('sales-empty').hidden = rows.length !== 0;
        element('sales-remove-heading').hidden = !permissions.delete;
        element('sales-line-count').textContent = String(cart.line_count);
        element('sales-summary-lines').textContent = String(cart.line_count);
        element('sales-summary-quantity').textContent = String(cart.quantity);
        element('sales-total').textContent = money(cart.total);
        state();
    }

    function expired(response) {
        if (response.status !== 401) return false;
        location.replace('/login');
        return true;
    }

    function accessLost() {
        lost = true; permissions = {}; cart = { items: [], line_count: 0, quantity: 0, total: '0.00' };
        input.value = ''; render(); onAccessLost();
    }

    async function authorize(action = 'view') {
        if (lost) return false;
        const result = await api('/api/modules/sales/access');
        if (expired(result.response)) return false;
        if (result.response.status === 403) { accessLost(); return false; }
        if (!result.response.ok) throw new Error('No se pudieron consultar los permisos.');
        permissions = result.data.actions;
        render();
        if (!permissions[action]) {
            await alertPermission('Tu grupo no tiene permiso para realizar esta acción en Ventas.');
            return false;
        }
        return true;
    }

    async function load() {
        if (!await authorize()) return;
        const result = await api('/api/sales/cart');
        if (expired(result.response)) return;
        if (result.response.status === 403) { accessLost(); return; }
        if (!result.response.ok) throw new Error('No se pudo cargar el carrito.');
        cart = result.data.data;
        ready = true;
        render();
        if (cart.removed_unavailable) await alertError('Se retiraron del carrito productos que ya no están disponibles.');
    }

    async function mutate(action, path, method, data) {
        if (!await authorize(action)) return;
        const csrf = await api('/api/csrf');
        if (!csrf.response.ok) throw new Error('No se pudo preparar la solicitud.');
        const result = await api(path, { method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.data.sales },
            ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
        if (expired(result.response)) return;
        if (result.response.status === 403) {
            if (await authorize()) await alertPermission();
            return;
        }
        if (!result.response.ok) {
            await alertError(result.data?.error ?? 'No se pudo modificar el carrito.');
            return;
        }
        cart = result.data.data;
        render();
        element('sales-scan-status').textContent = `${cart.quantity} ${cart.quantity === 1 ? 'unidad' : 'unidades'} en el carrito.`;
    }

    function enqueue(job) {
        pending++;
        state();
        chain = chain.then(async () => { if (!lost) await job(); }).catch(async () => {
            await alertError('No pudimos confirmar la operación. Actualiza el carrito antes de repetir la lectura para evitar sumar unidades de más.');
        }).finally(() => {
            pending--;
            state();
            if (!pending && !lost) element('sales-scan-status').textContent = `${cart.quantity} ${cart.quantity === 1 ? 'unidad' : 'unidades'} en el carrito.`;
            focusScanner();
            setTimeout(focusScanner, 250);
        });
        return chain;
    }

    function changeQuantity(id, quantity) {
        if (!Number.isInteger(quantity) || quantity < 1 || quantity > 9999) {
            render();
            void alertError('La cantidad debe ser un entero entre 1 y 9999.').then(() => setTimeout(focusScanner, 250));
            return;
        }
        enqueue(() => mutate('update', `/api/sales/cart/items/${id}`, 'PATCH', { quantity }));
    }

    async function checkout(status) {
        if (pending || !cart.items.length) return;
        if (status === 'paid' && !await confirmInvoicePayment()) return;
        await enqueue(async () => {
            if (!await authorize('create')) return;
            const csrf = await api('/api/csrf');
            if (!csrf.response.ok) throw new Error('No se pudo preparar el registro.');
            const result = await api('/api/sales/cart/checkout', {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.data.sales },
                body: JSON.stringify({ status, checkout_key: cart.checkout_key }),
            });
            if (expired(result.response)) return;
            if (!result.response.ok) { await alertError(result.data?.error ?? 'No se pudo guardar la venta.'); return; }
            cart = result.data.cart;
            render();
            await notifySuccess(`${result.data.data.number}: ${result.data.data.status === 'paid' ? 'facturada' : 'pendiente de pago'}. Disponible en Facturación.`);
        });
    }
    element('sales-pay').addEventListener('click', () => checkout('paid'));
    element('sales-pending').addEventListener('click', () => checkout('pending'));
    element('sales-scan-form').addEventListener('submit', (event) => {
        event.preventDefault();
        const barcode = input.value.trim();
        if (!barcode || !ready || lost) return;
        input.value = '';
        enqueue(() => mutate('create', '/api/sales/cart/items', 'POST', { barcode }));
        focusScanner();
    });
    element('sales-refresh').addEventListener('click', () => enqueue(load));
    element('sales-clear').addEventListener('click', async () => {
        if (pending || !cart.items.length) return;
        if (await confirmCartClear()) await enqueue(() => mutate('delete', '/api/sales/cart', 'DELETE'));
        focusScanner();
    });
    await enqueue(load);
}
