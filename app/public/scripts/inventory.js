import { api } from './api.js';
import { alertError, alertPermission, inventoryReceiptDialog, inventoryRemovalDialog, notifySuccess } from './alerts.js';

const element = (id) => document.getElementById(id);
const money = (value) => { const [whole, fraction = '00'] = String(value).split('.'); return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')}`; };

export async function startInventory({ actions, onAccessLost }) {
    let permissions = actions, busy = false, lost = false, page = 1, pages = 1, search = '';
    const state = () => {
        // Cada fila conserva su propio estado; busy se protege con el guard de run().
        if (lost) {
            for (const control of element('inventory-view').querySelectorAll('button, input')) control.disabled = true;
        }
        element('inventory-previous').disabled = busy || page <= 1;
        element('inventory-next').disabled = busy || page >= pages;
    };
    async function request(path, options) {
        const result = await api(path, options);
        if (result.response.status === 401) { location.replace('/login'); throw new Error('La sesión expiró.'); }
        if (!result.response.ok) throw new Error(result.data?.error ?? 'No se pudo completar la operación.');
        return result.data;
    }
    async function authorize(action = 'view') {
        const result = await api('/api/modules/inventory/access');
        if (result.response.status === 401) { location.replace('/login'); return false; }
        if (result.response.status === 403) { lost = true; onAccessLost(); return false; }
        if (!result.response.ok) throw new Error('No se pudieron consultar los permisos.');
        permissions = result.data.actions;
        if (!permissions[action]) { await alertPermission('Tu grupo ya no tiene permiso para realizar esta acción en Inventario.'); return false; }
        return true;
    }
    async function run(job) {
        if (busy || lost) return;
        busy = true; state();
        try { await job(); } catch (error) { await alertError(error.message); } finally { busy = false; state(); }
    }
    async function update(row, active, stock) {
        if (!await authorize('update')) return;
        const csrf = await request('/api/csrf');
        await request(`/api/inventory/${row.product_id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.inventory }, body: JSON.stringify({ active, stock }) });
        await notifySuccess(active ? `${row.name} ahora controla inventario.` : `${row.name} volvió a considerarse ilimitado.`);
        await load();
    }
    async function receive(row, quantity, totalCost) {
        if (!await authorize('update')) return;
        const csrf = await request('/api/csrf');
        await request('/api/inventory/' + row.product_id + '/receipts', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.inventory }, body: JSON.stringify({ quantity, total_cost: totalCost }) });
        await notifySuccess('Entrada registrada para ' + row.name + '.');
        await load();
    }
    async function remove(row, quantity, reason) {
        if (!await authorize('update')) return;
        const csrf = await request('/api/csrf');
        await request('/api/inventory/' + row.product_id + '/removals', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.inventory }, body: JSON.stringify({ quantity, reason }) });
        await notifySuccess('Salida registrada para ' + row.name + '.');
        await load();
    }
    async function load() {
        if (!await authorize()) return;
        element('inventory-loading').hidden = false; element('inventory-empty').hidden = true; element('inventory-table-container').hidden = true;
        const query = new URLSearchParams({ page, limit: 20 }); if (search) query.set('search', search);
        const result = await request(`/api/inventory?${query}`);
        pages = Math.max(1, Math.ceil(result.pagination.total / 20));
        if (page > pages) { page = pages; return load(); }
        const rows = result.data.map((row) => {
            const tr = document.createElement('tr');
            tr.append(Object.assign(document.createElement('td'), { textContent: row.name }), Object.assign(document.createElement('td'), { textContent: row.barcode, className: 'barcode-cell' }));
            const control = document.createElement('td');
            const switchLabel = document.createElement('label'); switchLabel.className = 'inventory-switch';
            const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = !row.unlimited; checkbox.disabled = !permissions.update; checkbox.setAttribute('aria-label', `Controlar inventario de ${row.name}`);
            const switchTrack = document.createElement('span'); switchTrack.className = 'inventory-switch-track'; switchTrack.setAttribute('aria-hidden', 'true');
            switchLabel.append(checkbox, switchTrack); control.append(switchLabel);
            const stockCell = Object.assign(document.createElement('td'), { textContent: String(row.stock) });
            const reserved = Object.assign(document.createElement('td'), { textContent: row.unlimited ? '—' : String(row.reserved) });
            const available = Object.assign(document.createElement('td'), { textContent: row.unlimited ? 'Ilimitado' : String(row.available) });
            const average = Object.assign(document.createElement('td'), { textContent: '$' + money(row.cost_price) });
            const actionCell = document.createElement('td'); actionCell.className = 'row-actions';
            const receiveButton = document.createElement('button'); receiveButton.type = 'button'; receiveButton.className = 'table-action'; receiveButton.textContent = 'Agregar'; receiveButton.disabled = row.unlimited || !permissions.update;
            const removeButton = document.createElement('button'); removeButton.type = 'button'; removeButton.className = 'table-action button-secondary'; removeButton.textContent = 'Retirar'; removeButton.disabled = row.unlimited || row.available < 1 || !permissions.update;
            actionCell.append(receiveButton, removeButton);
            checkbox.addEventListener('change', () => {
                // The buttons remain disabled until the server confirms the new state and reloads the row.
                receiveButton.disabled = true;
                removeButton.disabled = true;
                void run(() => update(row, checkbox.checked, row.stock));
            });
            receiveButton.addEventListener('click', () => void run(async () => {
                const values = await inventoryReceiptDialog(row.name, row.cost_price);
                if (values) await receive(row, values.quantity, values.totalCost);
            }));
            removeButton.addEventListener('click', () => void run(async () => {
                const values = await inventoryRemovalDialog(row.name, row.available);
                if (values) await remove(row, values.quantity, values.reason);
            }));
            tr.append(control, stockCell, average, reserved, available, actionCell); return tr;
        });
        element('inventory-rows').replaceChildren(...rows); element('inventory-loading').hidden = true; element('inventory-empty').hidden = result.data.length !== 0; element('inventory-table-container').hidden = result.data.length === 0;
        element('inventory-pagination').hidden = result.pagination.total === 0; element('inventory-range').textContent = result.pagination.total ? `${(page - 1) * 20 + 1}–${Math.min(page * 20, result.pagination.total)} de ${result.pagination.total} productos` : ''; element('inventory-page-number').textContent = `${page} de ${pages}`; state();
    }
    element('inventory-search-form').addEventListener('submit', (event) => { event.preventDefault(); search = element('inventory-search').value.trim(); page = 1; void run(load); });
    element('inventory-previous').addEventListener('click', () => { if (page > 1) { page--; void run(load); } });
    element('inventory-next').addEventListener('click', () => { if (page < pages) { page++; void run(load); } });
    await run(load);
}
