// SPDX-License-Identifier: Apache-2.0
// UMB-P07 (#144): the phone shows and changes the theme kept on the hub, and keeps the rest of the document.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';
import { Features, OP } from './api/client';
import { ApiError, type HomeView } from './api/types';
import { PrefsProvider } from './prefs';
import { AppearanceSection } from './screens/AppearanceSection';
import { SessionProvider, useSession, type SessionDeps } from './session';
import type { Connection } from './storage';
import { v0Api } from './test/fakes';
import { useIsDark } from './ui/theme';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const HOME: HomeView = {
  version: 3,
  layout: 'classic',
  appearance: { theme: 'dark', wallpaper: 'om-dusk-02', accent: 'wallpaper', density: 'compact', reduce_transparency: false, reduce_motion: 'system' },
  dock: ['sys:approvals', 'sys:apps'],
  grid: { order: [], hidden: [] },
  widgets: [],
  seen: {},
  updated_at: '2026-11-15T12:00:00Z',
};

function Gate({ children }: { children: React.ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}
function Dark() {
  return <Text testID="dark">{useIsDark() ? 'dark' : 'light'}</Text>;
}

async function mount(over: Parameters<typeof v0Api>[0], served = true) {
  const api = v0Api({ features: async () => new Features(served ? [OP.me, OP.homeGet] : [OP.me], 'openapi'), ...over });
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <PrefsProvider>
          <Dark />
          <AppearanceSection />
        </PrefsProvider>
      </Gate>
    </SessionProvider>,
  );
}

describe('hub-side preferences on the phone', () => {
  it('applies the theme from the hub and saves a change with If-Match, keeping the other fields', async () => {
    const saveHome = jest.fn(async (doc: unknown) => ({ home: { ...HOME, ...(doc as object) } as HomeView, etag: '"b"' }));
    await mount({ home: async () => ({ home: HOME, etag: '"a"' }), saveHome });
    await waitFor(() => expect(screen.getByTestId('dark').children.join('')).toBe('dark'));
    await fireEvent.press(await screen.findByTestId('theme-light'));
    await waitFor(() => expect(saveHome).toHaveBeenCalledTimes(1));
    const [doc, etag] = saveHome.mock.calls[0] as unknown as [HomeView, string];
    expect(etag).toBe('"a"');
    expect(doc.appearance?.theme).toBe('light');
    // Everything the phone does not edit is sent back unchanged, and the read-only timestamp is not.
    expect(doc.layout).toBe('classic');
    expect(doc.appearance?.wallpaper).toBe('om-dusk-02');
    expect(doc.dock).toEqual(['sys:approvals', 'sys:apps']);
    expect('updated_at' in doc).toBe(false);
    await waitFor(() => expect(screen.getByTestId('dark').children.join('')).toBe('light'));
  });

  it('when the desktop changed Home meanwhile (412) it reads again and applies only its own change', async () => {
    const theirs = { ...HOME, dock: ['sys:approvals'] };
    const saveHome = jest
      .fn()
      .mockRejectedValueOnce(new ApiError(412, 'stale_precondition', 'changed'))
      .mockImplementationOnce(async (doc: unknown) => ({ home: doc as HomeView, etag: '"c"' }));
    const home = jest.fn().mockResolvedValueOnce({ home: HOME, etag: '"a"' }).mockResolvedValueOnce({ home: theirs, etag: '"b"' });
    await mount({ home, saveHome });
    await fireEvent.press(await screen.findByTestId('theme-light'));
    await waitFor(() => expect(saveHome).toHaveBeenCalledTimes(2));
    const [doc, etag] = saveHome.mock.calls[1] as [HomeView, string];
    expect(etag).toBe('"b"');
    expect(doc.dock).toEqual(['sys:approvals']); // the desktop's change survived
    expect(doc.appearance?.theme).toBe('light');
  });

  it('shows nothing on a hub that keeps no preferences', async () => {
    await mount({}, false);
    expect(screen.queryByTestId('theme-light')).toBeNull();
    expect(screen.getByTestId('dark').children.join('')).toBe('light');
  });
});
