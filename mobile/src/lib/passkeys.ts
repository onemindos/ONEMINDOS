// SPDX-License-Identifier: Apache-2.0
// The phone's platform authenticator. Placeholder until the native adapter lands with its dependency.
import type { Passkeys } from './webauthn';

export function platformPasskeys(): Passkeys | undefined {
  return undefined;
}
