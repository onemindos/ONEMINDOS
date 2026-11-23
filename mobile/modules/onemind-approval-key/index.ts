// SPDX-License-Identifier: Apache-2.0
// JS side of the approval-key module (#703, Android first). On iPhone, in tests and in Expo Go the
// native module is absent and `approvalKeyNative` is undefined; callers treat that as "not on this phone".
import { requireOptionalNativeModule } from 'expo';

export type Biometrics = 'ok' | 'none_enrolled' | 'no_hardware' | 'update_required' | 'unavailable';
export type SecurityLevel = 'strongbox' | 'tee' | 'software';

export interface ApprovalKeyNative {
  status(): { biometrics: Biometrics; strongBoxAvailable: boolean; publicKey: string | null };
  /** New key (any old one is replaced): SubjectPublicKeyInfo DER, base64url. */
  create(): Promise<{ publicKey: string; securityLevel: SecurityLevel }>;
  /** System biometric prompt, then ECDSA P-256 SHA-256 over `payload` (UTF-8). DER, base64url. */
  sign(payload: string, title: string, subtitle: string): Promise<string>;
  remove(): void;
}

/** Native rejection codes (ApprovalKeyModule.kt). */
export type ApprovalKeyCode = 'ERR_CANCELLED' | 'ERR_NO_KEY' | 'ERR_KEY_INVALIDATED' | 'ERR_NO_BIOMETRIC' | 'ERR_LOCKOUT' | 'ERR_FAILED';

export const approvalKeyNative: ApprovalKeyNative | undefined =
  requireOptionalNativeModule<ApprovalKeyNative>('OneMindApprovalKey') ?? undefined;
