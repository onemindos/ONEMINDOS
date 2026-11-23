// SPDX-License-Identifier: Apache-2.0
// #715 My devices: one install id and one name for every credential this phone holds.
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import { loadThisPhone, renameThisPhone, resetThisPhoneForTests } from './install';

const ID = /^[A-Za-z0-9_-]{16,64}$/; // what the hub's install_id fields accept

beforeEach(async () => {
  resetThisPhoneForTests();
  await SecureStore.deleteItemAsync('onemind.install.v1');
});

it('makes a random install id once and keeps it across app starts', async () => {
  const first = await loadThisPhone();
  expect(first.installId).toMatch(ID);
  expect(first.name).toBe(Platform.OS === 'ios' ? 'iPhone' : 'Android phone');
  resetThisPhoneForTests(); // a new app start: read back from the secure store
  expect(await loadThisPhone()).toEqual(first);
});

it('gives two installs with the same default name two different ids', async () => {
  const a = await loadThisPhone((n) => new Uint8Array(n).fill(1));
  resetThisPhoneForTests();
  await SecureStore.deleteItemAsync('onemind.install.v1'); // a second phone: an empty secure store
  const b = await loadThisPhone((n) => new Uint8Array(n).fill(2));
  expect(a.name).toBe(b.name);
  expect(a.installId).not.toBe(b.installId);
});

it('a rename keeps the install id and is what the next credential carries', async () => {
  const before = await loadThisPhone();
  const after = await renameThisPhone("  Zeus's Pixel  ");
  expect(after).toEqual({ installId: before.installId, name: "Zeus's Pixel" });
  resetThisPhoneForTests();
  expect(await loadThisPhone()).toEqual(after);
  expect((await renameThisPhone('   ')).name).toBe(Platform.OS === 'ios' ? 'iPhone' : 'Android phone');
});

it('replaces an unreadable record with a fresh install', async () => {
  await SecureStore.setItemAsync('onemind.install.v1', '{"installId":"bad id"}');
  expect((await loadThisPhone()).installId).toMatch(ID);
});
