/** Keep literal manifest declarations available to the app manifest validator. */
export function defineApp(declarations) {
    return declarations;
}
export class AppClient {
    #gateway;
    #ownSecrets;
    constructor(gateway, ownSecrets = new Map()) {
        this.#gateway = gateway;
        this.#ownSecrets = ownSecrets;
    }
    requestAction(input) {
        return this.#gateway.actions.request(input);
    }
    fileRoots() {
        return this.#gateway.call({ method: 'GET', path: '/v1/files/roots', retry: true });
    }
    notify(body) {
        return this.#gateway.call({ method: 'POST', path: '/v1/notifications/send', body });
    }
    series(query) {
        const params = new URLSearchParams(Object.entries(query).map(([name, value]) => [name, String(value)]));
        return this.#gateway.call({ method: 'GET', path: `/v1/series?${params}`, retry: true });
    }
    /** Secrets already delivered by the host for this app. There is no app ID or gateway secret lookup. */
    ownSecret(name) {
        return this.#ownSecrets.get(name);
    }
}
