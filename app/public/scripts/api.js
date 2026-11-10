/** Same-origin session API. Handles JSON responses and empty DELETE responses. */
export async function api(path, options = {}) {
    const response = await fetch(path, {
        ...options,
        credentials: 'same-origin',
        headers: { Accept: 'application/json', ...options.headers },
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    return { response, data };
}
