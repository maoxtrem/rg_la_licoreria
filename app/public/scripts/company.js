import { api } from './api.js';
import { alertError, alertPermission, notifySuccess } from './alerts.js';

export async function startCompany({ onAccessLost }) {
    const element = (id) => document.getElementById(`company-${id}`);
    const fields = ['name', 'address', 'phone', 'nit'];
    let exists = false;
    let actions = {};
    let busy = false;
    let loaded = false;

    function controls() {
        const allowed = loaded && (exists ? actions.update : actions.create);
        element('fields').disabled = busy || !allowed;
        element('save').hidden = !allowed;
        element('save').disabled = busy;
        element('refresh').disabled = busy;
        element('save').textContent = exists ? 'Guardar cambios' : 'Registrar empresa';
    }

    async function access() {
        const result = await api('/api/modules/company/access');
        if (result.response.status === 401) {
            location.replace('/login');
            return false;
        }
        if (result.response.status === 403) {
            fields.forEach((field) => { element(field).value = ''; });
            loaded = false;
            onAccessLost();
            return false;
        }
        if (!result.response.ok) throw new Error('No se pudo consultar el acceso.');
        actions = result.data.actions;
        return true;
    }

    async function load() {
        if (busy) return;
        busy = true;
        controls();
        try {
            if (!await access()) return;
            const result = await api('/api/company');
            if (result.response.status === 401) { location.replace('/login'); return; }
            if (result.response.status === 403) { onAccessLost(); return; }
            if (!result.response.ok) throw new Error('No se pudieron cargar los datos de la empresa.');
            exists = result.data.data !== null;
            fields.forEach((field) => { element(field).value = result.data.data?.[field] ?? ''; });
            loaded = true;
            element('form').hidden = false;
            element('status').textContent = exists
                ? (actions.update ? 'Todos los campos son obligatorios.' : 'Datos de la empresa. Solo lectura.')
                : (actions.create ? 'Registra los datos de tu empresa. Todos los campos son obligatorios.' : 'Todavía no hay una empresa registrada. Solicita el permiso para registrarla.');
        } catch (error) {
            element('status').textContent = 'No se pudieron actualizar los datos. Inténtalo nuevamente.';
            await alertError(error.message);
        } finally {
            busy = false;
            controls();
        }
    }

    element('form').addEventListener('submit', async (event) => {
        event.preventDefault();
        if (busy || !loaded) return;
        busy = true;
        controls();
        fields.forEach((field) => {
            element(`${field}-error`).hidden = true;
            element(field).removeAttribute('aria-invalid');
        });
        try {
            if (!await access()) return;
            if (!(exists ? actions.update : actions.create)) {
                await alertPermission();
                return;
            }
            const csrf = await api('/api/csrf');
            if (!csrf.response.ok) throw new Error('No se pudo preparar el guardado.');
            const data = Object.fromEntries(fields.map((field) => [field, element(field).value]));
            const result = await api('/api/company', {
                method: exists ? 'PUT' : 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.data.company },
                body: JSON.stringify(data),
            });
            if (result.response.status === 401) { location.replace('/login'); return; }
            if (result.response.status === 403) {
                if (await access()) await alertPermission();
                return;
            }
            if (!result.response.ok) {
                for (const field of fields) {
                    if (!result.data.errors?.[field]) continue;
                    element(`${field}-error`).textContent = result.data.errors[field];
                    element(`${field}-error`).hidden = false;
                    element(field).setAttribute('aria-invalid', 'true');
                }
                throw new Error(result.data.error ?? 'No se pudieron guardar los datos.');
            }
            exists = true;
            fields.forEach((field) => { element(field).value = result.data.data[field]; });
            element('status').textContent = 'Datos de la empresa guardados.';
            await notifySuccess('Datos de la empresa guardados');
        } catch (error) {
            await alertError(error.message);
        } finally {
            busy = false;
            controls();
        }
    });
    element('refresh').addEventListener('click', load);
    await load();
}
