// SPDX-License-Identifier: Apache-2.0
// Tests only: a software P-256 key standing in for the Android Keystore key. Never imported by the app.
import { p256 } from '@noble/curves/nist.js';
import { utf8ToBytes } from '@noble/hashes/utils.js';
import type { ApprovalKeyNative } from '../../modules/onemind-approval-key';
import { toB64url } from '../lib/device';

const SPKI_HEAD = Uint8Array.from([
  0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01, 0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07, 0x03, 0x42, 0x00,
]);

/** A software stand-in for the Keystore key: same curve, same DER signatures as Android's SHA256withECDSA. */
export function fakeKey() {
  const secret = p256.utils.randomSecretKey();
  const spki = toB64url(Uint8Array.from([...SPKI_HEAD, ...p256.getPublicKey(secret, false)]));
  const signDer = (payload: string) => toB64url(p256.sign(utf8ToBytes(payload), secret, { format: 'der' }));
  const sign: ApprovalKeyNative['sign'] = async (payload) => signDer(payload);
  const native = {
    status: jest.fn(() => ({ biometrics: 'ok' as const, strongBoxAvailable: true, publicKey: spki })),
    create: jest.fn(async () => ({ publicKey: spki, securityLevel: 'strongbox' as const })),
    sign: jest.fn(sign),
    remove: jest.fn(),
  };
  return { spki, signDer, native: native as typeof native & ApprovalKeyNative };
}
