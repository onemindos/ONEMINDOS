// SPDX-License-Identifier: Apache-2.0
import type { OneMind, RequestActionInput, components, paths } from '@onemind/sdk';

type Series = NonNullable<paths['/v1/series']['get']['parameters']['query']>;
type Notify = components['schemas']['SendIn'];
type Declaration = Record<string, unknown>;

export interface AppDeclarations {
  tools?: readonly Declaration[];
  search?: Declaration;
  notifications?: readonly Declaration[];
  layers?: readonly Declaration[];
  settings?: Declaration;
}

/** Keep literal manifest declarations available to the app manifest validator. */
export function defineApp<T extends AppDeclarations>(declarations: T): T {
  return declarations;
}

export class AppClient {
  readonly #gateway: OneMind;
  readonly #ownSecrets: ReadonlyMap<string, string>;

  constructor(gateway: OneMind, ownSecrets: ReadonlyMap<string, string> = new Map()) {
    this.#gateway = gateway;
    this.#ownSecrets = ownSecrets;
  }

  requestAction(input: RequestActionInput) {
    return this.#gateway.actions.request(input);
  }

  fileRoots() {
    return this.#gateway.call<unknown>({ method: 'GET', path: '/v1/files/roots', retry: true });
  }

  notify(body: Notify) {
    return this.#gateway.call<unknown>({ method: 'POST', path: '/v1/notifications/send', body });
  }

  series(query: Series) {
    const params = new URLSearchParams(Object.entries(query).map(([name, value]) => [name, String(value)]));
    return this.#gateway.call<components['schemas']['SeriesPoint'][]>({ method: 'GET', path: `/v1/series?${params}`, retry: true });
  }

  /** Secrets already delivered by the host for this app. There is no app ID or gateway secret lookup. */
  ownSecret(name: string): string | undefined {
    return this.#ownSecrets.get(name);
  }
}
