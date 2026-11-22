// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { NO_STORAGE, toStorageStatus } from './homeStorage';

const AT = '2026-11-21T12:00:00Z';

describe('toStorageStatus', () => {
  it('reads state, encryption, used bytes and the disk count', () => {
    expect(toStorageStatus({ enabled: true, available: true, state: 'healthy', encrypted: true, used_bytes: 42, members: [{}, {}] }, AT)).toEqual({ state: 'healthy', encrypted: true, used_bytes: 42, disks: 2, observed_at: AT });
  });
  it('is empty, not an error, when the service is disabled or unavailable', () => {
    expect(toStorageStatus({ enabled: false, available: false }, AT)).toEqual(NO_STORAGE(AT));
    expect(toStorageStatus({ enabled: true, available: false }, AT)).toEqual(NO_STORAGE(AT));
  });
  it('drops values that are not plausible numbers and refuses non-objects', () => {
    expect(toStorageStatus({ enabled: true, available: true, used_bytes: -1 }, AT).used_bytes).toBeNull();
    expect(() => toStorageStatus([], AT)).toThrow(/invalid storage status/);
    expect(() => toStorageStatus({ enabled: 'yes' }, AT)).toThrow(/invalid storage status/);
  });
});
