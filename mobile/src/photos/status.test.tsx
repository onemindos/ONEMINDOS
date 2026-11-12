// SPDX-License-Identifier: Apache-2.0
// The words on the Backup screen, and the screen itself with a fake controller.
import { render, screen } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession } from '../session';
import { PhotoBackupContext, type PhotoBackupState } from './context';
import { DEFAULT_SETTINGS, type Ledger, type LedgerItem } from './ledger';
import { PhotoBackupScreen } from './PhotoBackupScreen';
import { summarize, type StatusInput } from './status';

jest.mock('@react-navigation/native', () => ({ useNavigation: () => ({ navigate: jest.fn() }) }));

const NOW = 1_800_000_000_000;
const item = (state: LedgerItem['state'], extra: Partial<LedgerItem> = {}): LedgerItem => ({ key: Math.random().toString(16), fileName: 'IMG.HEIC', modifiedAt: 1, inSelection: true, state, ...extra });

function ledger(items: LedgerItem[], more: Partial<Ledger> = {}): Ledger {
  return { version: 1, clientId: 'c', sourceId: 's', items: Object.fromEntries(items.map((x, i) => [`a${i}`, x])), scan: { at: NOW - 60_000, total: items.length }, ...more };
}

const base: StatusInput = {
  availability: { state: 'ok', baseUrl: 'https://box.example', demo: false },
  settings: { ...DEFAULT_SETTINGS, enabled: true },
  ledger: null,
  permission: 'granted',
  conditions: { network: 'wifi', power: 'battery' },
  running: false,
  now: NOW,
};

describe('summarize', () => {
  it('never claims a backup before anything was sent', () => {
    expect(summarize(base).headline).toBe('Not backed up yet');
    expect(summarize({ ...base, settings: DEFAULT_SETTINGS }).headline).toBe('Backup is off');
  });

  it('separates "on your OneMind" from backed up', () => {
    const v = summarize({ ...base, ledger: ledger([item('done'), item('done')], { lastComplete: NOW - 3_600_000 }) });
    expect(v.headline).toBe('All 2 selected items are on your OneMind');
    expect(v.tone).toBe('ok');
    expect(v.headline).not.toMatch(/backed up/i);
  });

  it('says what it waits for', () => {
    const l = ledger([item('done'), item('pending'), item('pending')]);
    expect(summarize({ ...base, ledger: l, conditions: { network: 'cellular', power: 'battery' } }).headline).toBe('2 waiting · waiting for Wi-Fi');
    expect(summarize({ ...base, ledger: l, settings: { ...base.settings, chargingOnly: true } }).cannotRun).toBe('Waiting for the phone to charge');
  });

  it('reports a dropped connection and failed items', () => {
    const l = ledger([item('pending'), item('failed', { error: 'iCloud only' })], {
      lastRun: { trigger: 'background', startedAt: NOW - 120_000, endedAt: NOW - 60_000, outcome: 'stopped', reason: 'connection_lost', uploaded: 0, deduped: 0, bytes: 0 },
    });
    const v = summarize({ ...base, ledger: l });
    expect(v.headline).toBe('1 waiting to be sent');
    expect(v.lines.join(' ')).toMatch(/1 could not be sent/);
    expect(v.lines.join(' ')).toMatch(/connection to your OneMind dropped; it will continue where it stopped/);
  });

  it('refuses plain HTTP and missing Photos with a reason', () => {
    expect(summarize({ ...base, availability: { state: 'needs_https', hubUrl: 'http://x' } })).toMatchObject({ headline: 'Backup needs a secure connection', tone: 'bad' });
    expect(summarize({ ...base, availability: { state: 'not_installed' } }).cannotRun).toBe('Photos is not installed');
    expect(summarize({ ...base, permission: 'denied' }).headline).toBe('OneMind cannot see your photos');
  });
});

function Gate({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

describe('PhotoBackupScreen', () => {
  it('shows status, live progress and the box coverage', async () => {
    const value: PhotoBackupState = {
      ...base,
      ledger: ledger([item('done'), item('pending')], { coverage: { total: 1, on_box: 1, backed_up: 1, verified: 0, as_of: '', fetchedAt: Date.now() } }),
      background: 'available',
      running: true,
      progress: { phase: 'uploading', done: 1, total: 2, current: { fileName: 'IMG_9.MOV', sent: 2_000_000, size: 8_000_000 }, bytesThisRun: 2_000_000 },
      host: 'box.example',
      demo: false,
      runNow: jest.fn(),
      stop: jest.fn(),
      updateSettings: jest.fn(),
      requestPermission: jest.fn(),
      loadAlbums: jest.fn(),
    };
    await render(
      <SessionProvider deps={{ load: async () => ({ mode: 'mock', token: 'owner-demo' }), save: async () => undefined, clear: async () => undefined }}>
        <Gate>
          <HubDataProvider intervalMs={0}>
            <PhotoBackupContext.Provider value={value}>
              <PhotoBackupScreen />
            </PhotoBackupContext.Provider>
          </HubDataProvider>
        </Gate>
      </SessionProvider>,
    );
    expect(await screen.findByText('Backing up…')).toBeTruthy();
    expect(screen.getByText('IMG_9.MOV · 2.0 MB of 8.0 MB')).toBeTruthy();
    expect(screen.getByText('Stop')).toBeTruthy();
    expect(screen.getByText('Backup restore-checked')).toBeTruthy();
    expect(screen.getByText(/never sent over plain HTTP/)).toBeTruthy();
  });
});
