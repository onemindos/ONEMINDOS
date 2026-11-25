// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { OneMind, OneMindError } from '@onemind/sdk';
import { recentItem, rememberVisit } from './homeRecent';

describe('Recent across devices', () => {
  it('records known permitted screens and app IDs without collecting private paths', () => {
    expect(recentItem('/files', 'pro', 'owner')).toBe('sys:files');
    expect(recentItem('/market/cloud-app', 'pro', 'adult')).toBe('app:cloud-app');
    expect(recentItem('/compose', 'pro', 'adult')).toBeUndefined();
    expect(recentItem('/network', 'simple', 'guest')).toBeUndefined();
    expect(recentItem('/private-note-name', 'pro', 'owner')).toBeUndefined();
    expect(recentItem('/', 'pro', 'owner')).toBeUndefined();
  });

  it('rebases a conflicting visit on the other device’s history and keeps all other Home fields', async () => {
    const sdk = new OneMind({ baseUrl: 'https://gateway.example.org' });
    const get = vi.spyOn(sdk.me.home, 'get')
      .mockResolvedValueOnce({ home: { version: 3, layout: 'desktop', recent: ['sys:market'] }, etag: '"1"' })
      .mockResolvedValueOnce({ home: { version: 3, layout: 'classic', recent: ['sys:settings', 'sys:files', 'sys:market'] }, etag: '"2"' });
    const save = vi.spyOn(sdk.me.home, 'save').mockRejectedValueOnce(new OneMindError(412, 'stale_precondition', 'Stale'))
      .mockResolvedValueOnce({ home: { version: 3, layout: 'desktop' }, etag: '"3"' });
    await rememberVisit(sdk.me.home, 'sys:files');
    expect(get).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith({ version: 3, layout: 'classic', recent: ['sys:files', 'sys:settings', 'sys:market'] }, '"2"');
  });
});
