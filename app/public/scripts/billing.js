import { api } from './api.js';
import { alertError, alertPermission, confirmInvoicePayment, notifySuccess } from './alerts.js';

const element = (id) => document.getElementById(id);
const money = (value) => {
    const [whole, fraction = '00'] = value.split('.');
    return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction.padEnd(2, '0')}`;
};
const cents = (value) => BigInt(value.replace('.', ''));
const decimal = (value) => `${value / 100n}.${String(value % 100n).padStart(2, '0')}`;

export async function startBilling({ actions, onAccessLost }) {
    let permissions = actions, busy = false, lost = false, page = 1, pages = 1;
    let editing = null, items = [];
    const dialog = element('billing-dialog');
    const detailDialog = element('billing-detail-dialog');
    let numberFilter = '';
    const dateParts = Object.fromEntries(new Intl.DateTimeFormat('en', {
        timeZone: 'America/Bogota', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(new Date()).map(({ type, value }) => [type, value]));
    const today = `${dateParts.year}-${dateParts.month}-${dateParts.day}`;
    for (const id of ['billing-date-from', 'billing-date-to']) element(id).value = today;
    // Keep a job reference after an uncertain response so retrying cannot duplicate it.
    const printJobs = new Map();
    function state() {
        for (const control of element('billing-view').querySelectorAll('button, input, select')) control.disabled = busy || lost;
        element('billing-previous').disabled = busy || page <= 1;
        element('billing-next').disabled = busy || page >= pages;
        element('billing-save').disabled = busy || !items.length || !permissions.update;
    }
    function close() { dialog.close(); detailDialog.close(); editing = null; items = []; }
    async function request(path, options) {
        const result = await api(path, options);
        if (result.response.status === 401) { location.replace('/login'); throw new Error('La sesión expiró.'); }
        if (!result.response.ok) throw new Error(result.data?.error ?? 'No se pudo completar la operación.');
        return result.data;
    }
    async function authorize(action = 'view') {
        const result = await api('/api/modules/billing/access');
        if (result.response.status === 401) { location.replace('/login'); return false; }
        if (result.response.status === 403) {
            lost = true; close(); element('billing-rows').replaceChildren(); onAccessLost(); return false;
        }
        if (!result.response.ok) throw new Error('No se pudieron consultar los permisos.');
        permissions = result.data.actions;
        if (!permissions[action]) {
            close(); await load(); await alertPermission('Tu grupo ya no tiene permiso para realizar esta acción en Facturación.'); return false;
        }
        return true;
    }
    async function run(job) {
        if (busy || lost) return;
        busy = true; state();
        try { await job(); }
        catch (error) { await alertError(error.message); }
        finally { busy = false; state(); }
    }
    async function mutate(path, method, data) {
        const csrf = await request('/api/csrf');
        return request(path, { method, headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.billing }, body: JSON.stringify(data) });
    }
    function cell(text, className = '') {
        const node = document.createElement('td'); node.textContent = text; node.className = className; return node;
    }
    function button(text, label, callback) {
        const node = document.createElement('button'); node.type = 'button'; node.className = 'table-action'; node.textContent = text;
        node.setAttribute('aria-label', label); node.addEventListener('click', callback); return node;
    }
    async function load() {
        const from = element('billing-date-from').value, to = element('billing-date-to').value;
        if (from && to && from > to) throw new Error('La fecha desde no puede ser posterior a la fecha hasta.');
        if (!await authorize()) return;
        element('billing-loading').hidden = false;
        try {
            const query = new URLSearchParams({ page, limit: 20, from, to });
            if (element('billing-status').value) query.set('status', element('billing-status').value);
            if (numberFilter) query.set('number', numberFilter);
            const result = await request(`/api/billing?${query}`);
            pages = Math.max(1, Math.ceil(result.pagination.total / 20));
            if (page > pages) { page = pages; return await load(); }
            const rows = result.data.map((invoice) => {
                const row = document.createElement('tr'); row.dataset.invoiceId = invoice.id;
                row.append(cell(invoice.number), cell(new Date(invoice.created_at).toLocaleString('es-CO', { timeZone: 'America/Bogota' })), cell(invoice.status === 'paid' ? 'Facturada' : 'Pendiente de pago'), cell(money(invoice.total), 'price-cell'));
                const controls = cell('', 'row-actions');
                controls.append(button('Ver contenido', `Ver contenido de ${invoice.number}`, () => run(() => show(invoice.id))));
                if (invoice.status === 'paid') {
                    controls.append(button('Imprimir', `Imprimir ${invoice.number}`, () => run(() => print(invoice.id))));
                } else if (permissions.update) {
                    controls.append(button('Editar', `Editar ${invoice.number}`, () => run(() => edit(invoice.id))), button('Pagar', `Pagar ${invoice.number}`, () => run(() => pay(invoice.id))));
                }
                row.append(controls); return row;
            });
            element('billing-rows').replaceChildren(...rows);
            element('billing-empty').hidden = rows.length !== 0;
            element('billing-table-container').hidden = rows.length === 0;
            element('billing-pagination').hidden = result.pagination.total === 0;
            element('billing-count').textContent = `${result.pagination.total} registros`;
            element('billing-page-number').textContent = `${page} de ${pages}`;
        } finally { element('billing-loading').hidden = true; state(); }
    }
    async function show(id) {
        if (!await authorize()) return;
        const { data } = await request(`/api/billing/${id}`);
        element('billing-detail-title').textContent = data.number;
        element('billing-detail-status').textContent = data.status === 'paid' ? 'Facturada' : 'Pendiente de pago';
        const date = (value) => new Date(value).toLocaleString('es-CO', { timeZone: 'America/Bogota' });
        element('billing-detail-date').textContent = `Creada: ${date(data.created_at)}` + (data.paid_at ? ` · Pagada: ${date(data.paid_at)}` : '');
        element('billing-detail-rows').replaceChildren(...data.items.map((item) => {
            const row = document.createElement('tr');
            row.append(cell(item.name), cell(item.quantity), cell(money(item.unit_price), 'price-cell'), cell(money(item.subtotal), 'price-cell'));
            return row;
        }));
        element('billing-detail-total').textContent = money(data.total);
        detailDialog.showModal();
    }
    async function edit(id) {
        if (!await authorize('update')) return;
        const { data } = await request(`/api/billing/${id}`);
        if (data.status !== 'pending') { await load(); throw new Error('La factura ya está facturada. Solo se puede imprimir.'); }
        editing = data; items = data.items.map((item) => ({ ...item }));
        element('billing-dialog-title').textContent = `Editar ${data.number}`;
        element('billing-barcode').value = '';
        renderItems(); dialog.showModal();
    }
    function renderItems() {
        let total = 0n;
        const rows = items.map((item) => {
            const subtotal = cents(item.unit_price) * BigInt(item.quantity); total += subtotal;
            const row = document.createElement('tr');
            const quantity = document.createElement('input'); quantity.type = 'number'; quantity.min = '1'; quantity.max = '9999'; quantity.step = '1'; quantity.required = true; quantity.value = item.quantity;
            quantity.setAttribute('aria-label', `Cantidad de ${item.name}`);
            quantity.addEventListener('change', () => {
                const value = Number(quantity.value);
                if (!Number.isInteger(value) || value < 1 || value > 9999) { quantity.reportValidity(); return; }
                item.quantity = value; renderItems();
            });
            const count = cell(''); count.append(quantity);
            const remove = cell(''); remove.append(button('Retirar', `Retirar ${item.name}`, () => { items = items.filter((line) => line !== item); renderItems(); }));
            row.append(cell(`${item.name} · ${money(item.unit_price)}`), count, cell(money(decimal(subtotal)), 'price-cell'), remove); return row;
        });
        element('billing-edit-rows').replaceChildren(...rows);
        element('billing-edit-total').textContent = money(decimal(total)); state();
    }
    async function pay(id) {
        if (!await authorize('update')) return;
        const { data } = await request(`/api/billing/${id}`);
        if (data.status !== 'pending') { await load(); throw new Error('La factura ya está facturada. Solo se puede imprimir.'); }
        if (!await confirmInvoicePayment()) return;
        try {
            await mutate(`/api/billing/${id}/pay`, 'POST', { revision: data.revision });
        } catch (error) { await load(); throw error; }
        await load(); await notifySuccess(`${data.number}: facturada. Ya puedes imprimirla.`);
    }
    async function print(id) {
        if (!await authorize()) return;
        if (!printJobs.has(id)) printJobs.set(id, Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join(''));
        await mutate(`/api/billing/${id}/print`, 'POST', { print_job_id: printJobs.get(id) });
        printJobs.delete(id);
        await notifySuccess('Solicitud enviada a la cola de impresión.');
    }
    element('billing-scan-form').addEventListener('submit', (event) => {
        event.preventDefault();
        void run(async () => {
            if (!await authorize('update') || !editing) return;
            const barcode = element('billing-barcode').value.trim();
            const { data } = await request(`/api/billing/product?${new URLSearchParams({ barcode })}`);
            const existing = items.find((item) => item.product_id === data.product_id);
            if (existing?.quantity >= 9999 || (!existing && items.length >= 100)) throw new Error('El registro admite hasta 100 productos y 9999 unidades por producto.');
            if (existing) existing.quantity++; else items.push(data);
            element('billing-barcode').value = ''; renderItems();
        }).then(() => { if (dialog.open) element('billing-barcode').focus(); });
    });
    element('billing-edit-form').addEventListener('submit', (event) => {
        event.preventDefault();
        void run(async () => {
            if (!await authorize('update') || !editing || !items.length) return;
            try {
                await mutate(`/api/billing/${editing.id}`, 'PATCH', { revision: editing.revision, items: items.map(({ product_id, quantity }) => ({ product_id, quantity })) });
            } catch (error) { close(); await load(); throw error; }
            close(); await load(); await notifySuccess('Registro pendiente actualizado.');
        });
    });
    for (const id of ['billing-close', 'billing-cancel']) element(id).addEventListener('click', close);
    dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); else close(); });
    for (const id of ['billing-detail-close', 'billing-detail-done']) element(id).addEventListener('click', () => detailDialog.close());
    detailDialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
    element('billing-number-filter').addEventListener('change', () => {
        void run(async () => { numberFilter = element('billing-number-filter').value.trim(); page = 1; await load(); });
    });
    element('billing-refresh').addEventListener('click', () => run(load));
    for (const id of ['billing-date-from', 'billing-date-to']) element(id).addEventListener('change', () => {
        page = 1; void run(load);
    });
    element('billing-status').addEventListener('change', () => { page = 1; void run(load); });
    element('billing-previous').addEventListener('click', () => { page--; void run(load); });
    element('billing-next').addEventListener('click', () => { page++; void run(load); });
    await run(load);
}
