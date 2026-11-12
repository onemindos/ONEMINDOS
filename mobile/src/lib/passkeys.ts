// SPDX-License-Identifier: Apache-2.0
// The phone's platform authenticator (Face ID / Touch ID on iPhone, Credential Manager on Android 14+)
// through react-native-passkey (MIT). On Android the app links only androidx.credentials (Apache-2.0):
// plugins/withoutPlayServicesCredentials.js removes the Play Services bridge, which is proprietary and
// only needed on Android 13 and older.
//
// The platform only lets an app use a passkey for a name (rpId) the app is linked to (iOS associated
// domains, Android asset links), fetched from that name over the public internet. A box at
// onemind.local cannot prove that, so passkeys work only once the app is linked to the name the box
// uses (mobile/README.md, "Passkeys"; a founder decision). Until then this reports `not_configured`.
import { Platform } from 'react-native';
import { assertionFrom, attestationFrom, PasskeyError, type PasskeyFailure, type Passkeys } from './webauthn';

type Lib = typeof import('react-native-passkey');
// The hub's transport hints are passed through as strings; the native side ignores unknown ones.
type GetReq = Parameters<Lib['Passkey']['get']>[0];
type CreateReq = Parameters<Lib['Passkey']['create']>[0];

const KIND: Record<string, PasskeyFailure> = {
  UserCancelled: 'cancelled',
  Interrupted: 'cancelled',
  NotSupported: 'not_supported',
  BadConfiguration: 'not_configured',
  NoCredentials: 'no_credentials',
};

export function toPasskeyError(e: unknown): PasskeyError {
  const code = (e as { error?: string } | null)?.error;
  const message = (e as { message?: string } | null)?.message ?? String(e);
  return new PasskeyError((code && KIND[code]) || 'failed', message);
}

let lib: Lib | null | undefined;
function load(): Lib | null {
  if (lib === undefined) {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      lib = require('react-native-passkey') as Lib;
    } catch {
      lib = null;
    }
  }
  return lib;
}

export function platformPasskeys(): Passkeys | undefined {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return undefined;
  const l = load();
  if (!l) return undefined;
  return {
    supported() {
      try {
        return l.Passkey.isSupported();
      } catch {
        return false;
      }
    },
    async get(options) {
      try {
        return assertionFrom(await l.Passkey.get(options as GetReq));
      } catch (e) {
        throw toPasskeyError(e);
      }
    },
    async create(options) {
      try {
        return attestationFrom(await l.Passkey.create(options as CreateReq));
      } catch (e) {
        throw toPasskeyError(e);
      }
    },
  };
}
