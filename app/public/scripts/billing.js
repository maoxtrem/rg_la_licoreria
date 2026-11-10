import { api } from './api.js';
import { alertError, alertPermission, confirmInvoicePayment, notifySuccess } from './alerts.js';

const money = (value) => {
    const [whole, fraction = '00'] = value.split('.');
    return '$' + whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ',' + fraction;
};
const cents = (value) => BigInt(value.replace('.', ''));
const decimal = (value) => `${value / 100n}.${String(value % 100n).padStart(2, '0')}`;
const jobId = () => [...crypto.getRandomValues(new Uint8Array(16))].map((value) => value.toString(16).padStart(2, '0')).join('');

export async function startBilling({ actions, onAccessLost }) {
    const element = (id) => document.getElementById(`billing-${id}`);
    let permissions = actions;
    let page = 1;
    let current = null;
    let lines = [];
    let dirty = false;
    let busy = false;
    let printId = null;
    const dialog = element('dialog');

    async function request(path, method = 'GET', data) {
        const headers = {};
        if (method !== 'GET') {
            const csrf = await api('/api/csrf');
            if (!csrf.response.ok) throw new Error('No se pudo preparar la solicitud.');
            headers['Content-Type'] = 'application/json';
            headers['X-CSRF-Token'] = csrf.data.billing;
        }
        const result = await api(path, { method, headers, ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
        if (result.response.status === 401) { location.replace('/login'); throw new Error('La sesión terminó.'); }
        if (result.response.status === 403) {
            const access = await api('/api/modules/billing/access');
            if (access.response.status === 403) {
                dialog.close(); current = null; lines = []; element('rows').replaceChildren(); element('items').replaceChildren(); onAccessLost();
            } else if (access.response.ok) {
                permissions = access.data.actions;
                if (current) renderDetail();
                await alertPermission();
            }
            throw new Error('No tienes permiso para esta acción.');
        }
        if (!result.response.ok) throw new Error(result.data?.error ?? 'No se pudo completar la solicitud.');
        return result.data;
    }

    async function run(work) {
        if (busy) return;
        busy = true;
        controls();
        try { await work(); } catch (error) { await alertError(error.message); }
        finally { busy = false; controls(); }
    }

    function controls() {
        element('refresh').disabled = busy;
        element('filter').disabled = busy;
        for (const id of ['save', 'pay', 'print']) element(id).disabled = busy || (id === 'pay' && dirty);
        for (const node of element('items').querySelectorAll('button,input')) node.disabled = busy;
        for (const node of element('add-form').querySelectorAll('button,input')) node.disabled = busy;
        for (const node of element('rows').querySelectorAll('button')) node.disabled = busy;
        element('close').disabled = busy;
    }

    async function load() {
        const filter = element('filter').value;
        const result = await request(`/api/billing?page=${page}&limit=20${filter ? '&status=' + filter : ''}`);
        const rows = result.data.map((invoice) => {
            const row = document.createElement('tr');
            row.dataset.invoiceId = invoice.id;
            for (const value of [invoice.number, new Date(invoice.created_at).toLocaleString('es-CO', { timeZone: 'America/Bogota' }), invoice.status === 'paid' ? 'Facturada' : 'Pendiente de pago', money(invoice.total)]) {
                const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
            }
            const cell = document.createElement('td');
            const button = document.createElement('button'); button.type = 'button'; button.className = 'table-action';
            button.textContent = invoice.status === 'paid' ? 'Ver / Imprimir' : 'Ver pendiente';
            button.addEventListener('click', () => run(() => open(invoice.id)));
            cell.append(button); row.append(cell);
            return row;
        });
        element('rows').replaceChildren(...rows);
        element('status').textContent = rows.length ? `${result.pagination.total} registros.` : 'No hay registros para este estado.';
        element('page').textContent = `Página ${page}`;
        element('previous').disabled = page <= 1;
        element('next').disabled = page * 20 >= result.pagination.total;
    }

    async function open(id) {
        current = (await request(`/api/billing/${id}`)).data;
        lines = current.items.map((line) => ({ ...line }));
        dirty = false; printId = null;
        renderDetail();
        if (!dialog.open) dialog.showModal();
    }

    function renderDetail() {
        const editable = current.status === 'pending' && permissions.update;
        element('title').textContent = current.number;
        element('detail-status').textContent = current.status === 'paid' ? 'Facturada · Pago registrado · Solo impresión' : 'Pendiente de pago';
        element('company').textContent = current.company ? `${current.company.name} · NIT ${current.company.nit} · ${current.company.address} · ${current.company.phone}` : '';
        const items = lines.map((line) => {
            const row = document.createElement('div'); row.className = 'catalog-toolbar';
            const name = document.createElement('span'); name.textContent = `${line.name} · ${money(line.unit_price)}`;
            row.append(name);
            if (editable) {
                const quantity = document.createElement('input'); quantity.type = 'number'; quantity.min = '1'; quantity.max = '9999'; quantity.step = '1'; quantity.value = line.quantity;
                quantity.setAttribute('aria-label', `Cantidad de ${line.name}`);
                quantity.addEventListener('change', () => {
                    const value = Number(quantity.value);
                    if (!Number.isInteger(value) || value < 1 || value > 9999) { quantity.value = line.quantity; void alertError('Usa una cantidad entre 1 y 9999.'); return; }
                    line.quantity = value; dirty = true; renderDetail();
                });
                const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'table-action table-action-danger'; remove.textContent = 'Retirar';
                remove.setAttribute('aria-label', `Retirar ${line.name}`);
                remove.addEventListener('click', () => { lines = lines.filter((item) => item.product_id !== line.product_id); dirty = true; renderDetail(); });
                row.append(quantity, remove);
            } else {
                const quantity = document.createElement('span'); quantity.textContent = `${line.quantity} unidades`; row.append(quantity);
            }
            const subtotal = document.createElement('strong'); subtotal.textContent = money(decimal(cents(line.unit_price) * BigInt(line.quantity))); row.append(subtotal);
            return row;
        });
        element('items').replaceChildren(...items);
        const total = lines.reduce((value, line) => value + cents(line.unit_price) * BigInt(line.quantity), 0n);
        element('total').textContent = `Total: ${money(decimal(total))}`;
        element('save').hidden = !editable;
        element('pay').hidden = !editable;
        element('print').hidden = current.status !== 'paid';
        element('add-form').hidden = !editable;
        element('notice').textContent = dirty ? 'Guarda los cambios antes de pagar.' : current.status === 'paid' ? 'La impresión se envía a la cola y la procesa el worker.' : 'Puedes editar este registro hasta confirmar el pago.';
        controls();
    }

    element('save').addEventListener('click', () => run(async () => {
        const result = await request(`/api/billing/${current.id}`, 'PATCH', { revision: current.revision, items: lines.map(({ product_id, quantity }) => ({ product_id, quantity })) });
        current = result.data; lines = current.items.map((line) => ({ ...line })); dirty = false;
        renderDetail(); await load(); await notifySuccess('Pendiente actualizado');
    }));
    element('pay').addEventListener('click', () => run(async () => {
        if (dirty || !await confirmInvoicePayment()) return;
        current = (await request(`/api/billing/${current.id}/pay`, 'POST', { revision: current.revision })).data;
        lines = current.items.map((line) => ({ ...line })); dirty = false;
        renderDetail(); await load(); await notifySuccess('Pago registrado. Factura cerrada.');
    }));
    element('print').addEventListener('click', () => run(async () => {
        printId ??= jobId();
        await request(`/api/billing/${current.id}/print`, 'POST', { print_job_id: printId });
        printId = null;
        element('notice').textContent = 'Impresión enviada a la cola. El worker la procesará; esto todavía no confirma la salida del papel.';
        await notifySuccess('Impresión enviada al worker');
    }));
    element('add-form').addEventListener('submit', (event) => {
        event.preventDefault();
        void run(async () => {
            const code = element('barcode').value.trim();
            const product = (await request('/api/billing/product?barcode=' + encodeURIComponent(code))).data;
            const existing = lines.find((line) => line.product_id === product.product_id);
            if (existing) {
                if (existing.quantity >= 9999) throw new Error('La cantidad máxima es 9999.');
                existing.quantity++;
            } else {
                if (lines.length >= 100) throw new Error('El máximo es 100 productos.');
                lines.push(product);
            }
            dirty = true; element('barcode').value = ''; renderDetail();
        });
    });
    element('close').addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', (event) => { if (busy) event.preventDefault(); });
    element('refresh').addEventListener('click', () => run(load));
    element('filter').addEventListener('change', () => { page = 1; void run(load); });
    element('previous').addEventListener('click', () => { if (!busy && page > 1) { page--; void run(load); } });
    element('next').addEventListener('click', () => { if (!busy) { page++; void run(load); } });
    await run(load);
}
