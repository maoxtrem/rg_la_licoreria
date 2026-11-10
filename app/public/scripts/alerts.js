import Swal from '../vendor/sweetalert2/sweetalert2.esm.all.min.js';

const image = '/images/access-denied.svg';
const theme = {
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
