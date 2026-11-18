import Swal from '../vendor/sweetalert2/sweetalert2.esm.all.min.js';

const image = '/images/access-denied.svg';
const theme = {
    background: '#fffdf9', color: '#302b29',
    confirmButtonText: 'Entendido',
    cancelButtonText: 'Cancelar',
    buttonsStyling: false,
    customClass: {
        popup: 'licoreria-alert',
        confirmButton: 'button',
        cancelButton: 'button-secondary',
        actions: 'licoreria-alert-actions',
    },
    // Native form dialogs occupy the top layer; alerts must be mounted inside it.
    target: () => document.querySelector('dialog[open]') ?? document.body,
};

function options(extra = {}) {
    return { ...theme, target: theme.target(), ...extra };
}

export function alertError(text, title = 'No pudimos completar la acción') {
    return Swal.fire(options({ icon: 'error', title, text }));
}

export function alertPermission(text = 'Solicita al administrador que revise los permisos de tu grupo.') {
    return Swal.fire(options({ title: 'Acceso restringido', text, imageUrl: image, imageWidth: 260, imageAlt: 'Una puerta cerrada con un candado' }));
}

export function notifySuccess(text) {
    return Swal.fire(options({
        toast: true, position: 'top-end', icon: 'success', title: text,
        showConfirmButton: false, timer: 3000, timerProgressBar: true,
        returnFocus: false,
    }));
}

export async function confirmDelete(name) {
    const result = await Swal.fire(options({
        icon: 'warning', title: '¿Eliminar este producto?',
        text: `Vas a eliminar «${name}». Esta acción no se puede deshacer.`,
        showCancelButton: true, confirmButtonText: 'Eliminar producto', cancelButtonText: 'Conservar producto',
        focusCancel: true,
        customClass: { ...theme.customClass, confirmButton: 'button button-danger' },
    }));
    return result.isConfirmed;
}

export async function confirmInvoiceCancel(number) {
    const result = await Swal.fire(options({
        icon: 'warning', title: '¿Cancelar el registro pendiente?',
        text: `Se liberará el inventario reservado por ${number}.`,
        showCancelButton: true, confirmButtonText: 'Cancelar registro', cancelButtonText: 'Conservar registro',
        focusCancel: true,
    }));
    return result.isConfirmed;
}

export async function inventoryReceiptDialog(name, baseCost) {
    const quantity = document.createElement('input');
    quantity.type = 'number'; quantity.min = '1'; quantity.step = '1'; quantity.max = '2147483647'; quantity.placeholder = 'Cantidad recibida';
    const total = document.createElement('input');
    total.type = 'number'; total.min = '0'; total.step = '100'; total.max = '2147483647'; total.placeholder = 'Costo total del lote (COP)';
    const hint = document.createElement('p'); hint.className = 'field-help'; hint.textContent = 'Costo actual de referencia: $' + Number(baseCost).toLocaleString('es-CO') + ' por unidad.';
    const content = document.createElement('div'); content.className = 'inventory-alert-form';
    const product = document.createElement('p'); product.textContent = name;
    product.className = 'inventory-alert-product';
    quantity.className = 'inventory-alert-field'; total.className = 'inventory-alert-field';
    quantity.setAttribute('aria-label', 'Cantidad recibida'); total.setAttribute('aria-label', 'Costo total del lote');
    content.append(product, quantity, total, hint);
    const result = await Swal.fire(options({
        icon: 'question', title: 'Agregar existencias', text: name, html: content,
        showCancelButton: true, confirmButtonText: 'Registrar entrada', cancelButtonText: 'Cancelar',
        didOpen: () => quantity.focus(),
        preConfirm: () => {
            const count = Number(quantity.value), cost = Number(total.value);
            if (!Number.isInteger(count) || count < 1 || !Number.isInteger(cost) || cost < 0) {
                Swal.showValidationMessage('Ingresa una cantidad válida y el costo total del lote.');
                return false;
            }
            return { quantity: count, totalCost: cost };
        },
    }));
    if (!result.isConfirmed) return null;
    const values = result.value;
    const unitCost = values.totalCost / values.quantity;
    if (Number(baseCost) > 0 && unitCost < Number(baseCost) * 0.8) {
        const warning = await Swal.fire(options({
            icon: 'warning', title: 'Posible costo incorrecto',
            text: 'El costo unitario calculado es $' + Math.round(unitCost).toLocaleString('es-CO') + ', más de 20% por debajo del costo actual de $' + Number(baseCost).toLocaleString('es-CO') + '.',
            showCancelButton: true, confirmButtonText: 'Continuar de todas formas', cancelButtonText: 'Revisar datos',
            focusCancel: true,
        }));
        if (!warning.isConfirmed) return null;
    }
    return values;
}

export async function inventoryRemovalDialog(name, available) {
    const quantity = document.createElement('input');
    quantity.type = 'number'; quantity.min = '1'; quantity.max = String(Math.max(0, available)); quantity.step = '1'; quantity.placeholder = 'Cantidad a retirar';
    const content = document.createElement('div');
    const product = document.createElement('p'); product.textContent = name;
    content.className = 'inventory-alert-form'; product.className = 'inventory-alert-product';
    quantity.className = 'inventory-alert-field'; quantity.setAttribute('aria-label', 'Cantidad a retirar');
    const reason = document.createElement('textarea'); reason.className = 'inventory-alert-field inventory-alert-reason'; reason.maxLength = 255; reason.placeholder = 'Motivo del retiro'; reason.setAttribute('aria-label', 'Motivo del retiro');
    const help = document.createElement('p'); help.className = 'field-help'; help.textContent = 'Disponible para retirar: ' + available + ' unidades.';
    content.append(product, quantity, reason, help);
    const result = await Swal.fire(options({
        icon: 'warning', title: 'Retirar existencias', text: name, html: content,
        showCancelButton: true, confirmButtonText: 'Retirar unidades', cancelButtonText: 'Cancelar',
        didOpen: () => quantity.focus(),
        preConfirm: () => {
            const count = Number(quantity.value);
            const reasonText = reason.value.trim();
            if (!Number.isInteger(count) || count < 1 || count > available) {
                Swal.showValidationMessage('La cantidad debe estar entre 1 y ' + available + '.');
                return false;
            }
            if (!reasonText) {
                Swal.showValidationMessage('Escribe el motivo del retiro.');
                reason.focus();
                return false;
            }
            return { quantity: count, reason: reasonText };
        },
    }));
    return result.isConfirmed ? result.value : null;
}


export function showLoading(title) {
    return Swal.fire(options({ title, allowOutsideClick: false, allowEscapeKey: false, didOpen: () => Swal.showLoading() }));
}

export function closeAlert() {
    Swal.close();
}


export async function confirmCartClear() {
    const result = await Swal.fire(options({
        icon: 'question', title: '¿Vaciar el carrito?', text: 'Se retirarán todos los productos de la venta actual.',
        showCancelButton: true, confirmButtonText: 'Vaciar carrito', cancelButtonText: 'Conservar carrito', focusCancel: true,
    }));
    return result.isConfirmed;
}

export async function confirmInvoicePayment(total) {
    const cents = (value) => BigInt(value.replace('.', ''));
    const decimal = (value) => `${value / 100n}.${String(value % 100n).padStart(2, '0')}`;
    const money = (value) => {
        const [whole, fraction] = value.split('.');
        return `$${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction}`;
    };
    const parse = (value) => {
        const text = value.trim().replace(',', '.');
        if (!/^\d{1,15}(?:\.\d{1,2})?$/.test(text)) return null;
        const [whole, fraction = ''] = text.split('.');
        return `${whole}.${fraction.padEnd(2, '0')}`;
    };
    const content = document.createElement('div');
    const summary = document.createElement('p');
    summary.textContent = `Total a pagar: ${money(total)} COP`;
    const transferLabel = document.createElement('label');
    transferLabel.htmlFor = 'payment-transfer-received'; transferLabel.textContent = 'Transferencia (COP)';
    const transfer = document.createElement('input');
    transfer.id = 'payment-transfer-received'; transfer.type = 'text'; transfer.inputMode = 'decimal';
    transfer.autocomplete = 'off'; transfer.maxLength = 18; transfer.value = '0.00';
    const label = document.createElement('label');
    label.htmlFor = 'payment-cash-received'; label.textContent = 'Efectivo recibido (COP)';
    const input = document.createElement('input');
    input.id = 'payment-cash-received'; input.type = 'text'; input.inputMode = 'decimal';
    input.autocomplete = 'off'; input.maxLength = 18; input.value = total;
    const change = document.createElement('p');
    change.id = 'payment-change'; change.setAttribute('aria-live', 'polite');
    const update = () => {
        const received = parse(input.value), transferred = parse(transfer.value);
        if (received === null || transferred === null) {
            change.textContent = 'Ingresa los importes sin separadores de miles.';
        } else if (cents(transferred) > cents(total)) {
            change.textContent = 'La transferencia no puede superar el total de la factura.';
        } else {
            const difference = cents(received) + cents(transferred) - cents(total);
            change.textContent = difference < 0n ? `Faltan: ${money(decimal(-difference))}`
                : `Cambio a devolver: ${money(decimal(difference))}`;
        }
    };
    input.addEventListener('input', update);
    transfer.addEventListener('input', () => {
        const transferred = parse(transfer.value);
        if (transferred !== null && cents(transferred) <= cents(total)) {
            input.value = decimal(cents(total) - cents(transferred));
        }
        Swal.resetValidationMessage(); update();
    });
    update();
    content.append(summary, transferLabel, transfer, label, input, change);
    const result = await Swal.fire(options({
        icon: 'question', title: 'Registrar pago', html: content,
        showCancelButton: true, confirmButtonText: 'Confirmar pago',
        didOpen: () => input.focus(),
        preConfirm: () => {
            const received = parse(input.value), transferred = parse(transfer.value);
            if (received === null || transferred === null || cents(transferred) > cents(total)
                || cents(received) + cents(transferred) < cents(total)) {
                Swal.showValidationMessage('Revisa efectivo y transferencia: deben cubrir el total y la transferencia no puede superarlo.');
                return false;
            }
            return { cash_received: received, transfer_received: transferred };
        },
    }));
    return result.isConfirmed ? result.value : null;
}
