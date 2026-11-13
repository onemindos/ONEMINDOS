// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Features, OP } from '../api/client';
import { ApiError, type FirstRunSettings } from '../api/types';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { BoxSettingsSection } from './BoxSettingsSection';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const FRESH: FirstRunSettings = { box_name: null, time_zone: null, backup_choice: 'later', backup_destination_id: null, saved: false };
const USB = { id: 'dst_0000000000000001', kind: 'usb', label: 'Blue USB disk' };

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

function deps(api: ReturnType<typeof v0Api>): SessionDeps {
  return { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
}

async function mount(over: Parameters<typeof v0Api>[0]) {
  const api = v0Api({
    features: async () => new Features([OP.onboardingSettings, OP.backupDestinations], 'openapi'),
    backupDestinations: async () => [USB],
    ...over,
  });
  await render(
    <SessionProvider deps={deps(api)}>
      <Gate>
        <BoxSettingsSection />
      </Gate>
    </SessionProvider>,
  );
  return api;
}

describe('first-run settings section', () => {
  it('loads the saved values and saves a full replacement', async () => {
    const save = jest.fn(async (b) => ({ ...b, saved: true }));
    await mount({ onboardingSettings: async () => FRESH, saveOnboardingSettings: save });
    await screen.findByTestId('box-settings');
    expect(screen.getByTestId('save-box-settings')).toBeDisabled(); // an empty name is not valid
    await fireEvent.changeText(screen.getByTestId('box-name'), 'Home');
    await fireEvent.changeText(screen.getByTestId('time-zone'), 'Europe/Berlin');
    await fireEvent.press(screen.getByTestId('choice-usb'));
    await fireEvent.press(screen.getByTestId('dest-dst_0000000000000001'));
    await fireEvent.press(screen.getByTestId('save-box-settings'));
    expect(await screen.findByText(/does not start a backup or set one up/)).toBeTruthy();
    expect(save).toHaveBeenCalledWith({ box_name: 'home', time_zone: 'Europe/Berlin', backup_choice: 'usb', backup_destination_id: USB.id });
  });

  it('says so in the card that backups are not started by saving', async () => {
    await mount({ onboardingSettings: async () => FRESH });
    expect(await screen.findByText(/does not start backups, add a destination or issue a recovery kit/)).toBeTruthy();
  });

  it('a non-owner (403 from the hub) sees an owner-only notice and no form', async () => {
    await mount({
      onboardingSettings: async () => {
        throw new ApiError(403, 'permission_denied', 'owner only');
      },
    });
    expect(await screen.findByText(/Only an owner can see or change/)).toBeTruthy();
    expect(screen.queryByTestId('box-settings')).toBeNull();
  });

  it('a refused save (403) turns the form off and does not claim success', async () => {
    const save = jest.fn(async () => {
      throw new ApiError(403, 'permission_denied', 'owner only');
    });
    await mount({ onboardingSettings: async () => ({ ...FRESH, box_name: 'home', time_zone: 'UTC' }), saveOnboardingSettings: save });
    await fireEvent.press(await screen.findByTestId('save-box-settings'));
    expect(await screen.findByText(/Only an owner can see or change/)).toBeTruthy();
    expect(screen.queryByText(/Saved/)).toBeNull();
  });

  it('shows nothing on a hub without the route', async () => {
    const api = v0Api();
    await render(
      <SessionProvider deps={deps(api)}>
        <Gate>
          <BoxSettingsSection />
        </Gate>
      </SessionProvider>,
    );
    expect(screen.queryByTestId('box-settings')).toBeNull();
  });

  it('hides the form for a demo adult, who is known not to be an owner', async () => {
    await render(
      <SessionProvider deps={{ load: async () => ({ mode: 'mock', token: 'adult-demo' }), save: async () => undefined, clear: async () => undefined }}>
        <Gate>
          <BoxSettingsSection />
        </Gate>
      </SessionProvider>,
    );
    expect(screen.queryByTestId('box-settings')).toBeNull();
  });
});
