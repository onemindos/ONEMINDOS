// SPDX-License-Identifier: Apache-2.0
import { ApiError } from '../api/types';
import type { WiringApi } from '../api/wiring';
import { askBoxCode } from './boxcode';
import { createPasskey } from './webauthn';

type Registration<Result> = Pick<WiringApi, 'passkeyRegisterOptions'> & {
  passkeyRegister(...args: Parameters<WiringApi['passkeyRegister']>): Promise<Result>;
};

/** Only the gateway can tell if a key is proven. A retry needs new options and a new credential. */
export async function registerPasskey<Result>(api: Registration<Result>, label?: string, needsBox?: () => void): Promise<Result> {
  const initial = await api.passkeyRegisterOptions();
  const credential = await createPasskey(initial.publicKey);
  try {
    return await api.passkeyRegister(credential, label);
  } catch (e) {
    if (!(e instanceof ApiError && e.reason === 'box_code_required')) throw e;
  }
  needsBox?.();
  const retry = await api.passkeyRegisterOptions();
  const code = retry.box_code_if_proven ? await askBoxCode('add a proven key') : undefined;
  return api.passkeyRegister(await createPasskey(retry.publicKey), label, code);
}
