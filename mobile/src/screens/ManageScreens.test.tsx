// SPDX-License-Identifier: Apache-2.0
// Backups, Automation, Files and Migration screens against a fake gateway.
import { NavigationContainer } from '@react-navigation/native';
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactElement, ReactNode } from 'react';
import { Features, OP } from '../api/client';
import { ApiError, type Action } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { AutomationScreen, triggerText } from './AutomationScreen';
import { BackupsScreen } from './BackupsScreen';
import { FilesScreen, join, parentOf } from './FilesScreen';
import { MigrateScreen } from './MigrateScreen';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const ALL = [OP.me, OP.backupStatus, OP.backupDestinations, OP.backupRuns, OP.backupRequestRun, OP.automationRules, OP.filesRoots, OP.migratePlans];
const OWNER_ME = { principal: { id: 'owner', kind: 'person' as const, role: 'owner' as const }, token: null, session: null, passkeys: 0, capabilities: ['can_approve', 'can_request'] };
const ADULT_ME = { principal: { id: 'alex', kind: 'person' as const, role: 'adult' as const }, token: null, session: null, passkeys: 0, capabilities: [] };
const forbidden = async () => {
  throw new ApiError(403, 'permission_denied', 'no');
};

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(ui: ReactElement, over: Parameters<typeof v0Api>[0] = {}) {
  const api = v0Api({ features: async () => new Features(ALL, 'openapi'), me: async () => OWNER_ME, actions: async () => [], ...over });
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <HubDataProvider intervalMs={0}>
          <NavigationContainer>{ui}</NavigationContainer>
        </HubDataProvider>
      </Gate>
    </SessionProvider>,
  );
  return api;
}

const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString();

describe('Backups screen', () => {
  const base = {
    backupStatus: async () => ({ health: 'ok', last_success_at: ago(3600), last_verified_restore_at: ago(86400), copies: 2, badges: { box: { state: 'verified' }, apps: { vaultwarden: { state: 'stale' } } } }),
    backupDestinations: async () => [{ id: 'dst_0000000000000001', kind: 'usb', label: 'Blue USB disk', primary: true, free_bytes: 400_000_000_000 }],
    backupRuns: async () => [{ id: 'run1', state: 'succeeded', started_at: ago(3700), reason: 'scheduled' }],
  };

  it('shows health, destinations and recent runs', async () => {
    await mount(<BackupsScreen />, base);
    expect(await screen.findByText('Protected')).toBeTruthy();
    expect(screen.getByText('box verified')).toBeTruthy();
    expect(screen.getByText('vaultwarden: stale')).toBeTruthy();
    expect(screen.getByText('Blue USB disk')).toBeTruthy();
    expect(screen.getByText('400 GB free')).toBeTruthy();
    expect(screen.getByTestId('run-run1')).toBeTruthy();
  });

  it('"Back up now" only files a request and shows it waiting for approval', async () => {
    const filed: Action = { id: 'act-5', type: 'backup.run', params: {}, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval' };
    const requestBackupRun = jest.fn(async () => filed);
    await mount(<BackupsScreen />, { ...base, requestBackupRun, actions: async () => [filed] });
    await fireEvent.press(await screen.findByTestId('backup-run'));
    expect(await screen.findByText(/No backup has started: it waits in Approvals/)).toBeTruthy();
    expect(screen.getAllByText('awaiting approval').length).toBeGreaterThan(0);
    expect(requestBackupRun).toHaveBeenCalledWith(expect.objectContaining({ idempotencyKey: expect.any(String) }));
  });

  it('"Check latest backup" files a verify request', async () => {
    const requestBackupVerify = jest.fn(async () => ({ id: 'act-6', type: 'backup.verify', params: {}, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval' as const }));
    await mount(<BackupsScreen />, { ...base, requestBackupVerify });
    await fireEvent.press(await screen.findByTestId('backup-verify'));
    expect(await screen.findByText(/No backup has started/)).toBeTruthy();
    expect(requestBackupVerify).toHaveBeenCalledTimes(1);
  });

  it('a 403 on the request is explained, not hidden', async () => {
    await mount(<BackupsScreen />, { ...base, requestBackupRun: forbidden });
    await fireEvent.press(await screen.findByTestId('backup-run'));
    expect(await screen.findByText(/Only an owner can/)).toBeTruthy();
  });

  it('an adult cannot ask: the buttons are off and the reason is given', async () => {
    await mount(<BackupsScreen />, { ...base, me: async () => ADULT_ME });
    expect(await screen.findByText(/Only an owner \(or an agent\) can ask for a backup/)).toBeTruthy();
    expect(screen.getByTestId('backup-run')).toBeDisabled();
  });

  it('a failing box says Failing', async () => {
    await mount(<BackupsScreen />, { ...base, backupStatus: async () => ({ health: 'failing' }) });
    expect(await screen.findByText('Failing')).toBeTruthy();
  });
});

describe('Automation screen', () => {
  const rule = (over = {}) => ({ id: 'r1', name: 'Nightly photo backup', enabled: true, trigger: { schedule: { cron: '0 3 * * *', tz: 'box' } }, last_fired_at: ago(7200), breaker: 'closed', ...over });
  const base = { automationState: async () => ({ paused: false }), automationRules: async () => [rule()], automationRuns: async () => [{ id: 'f1', fired_at: ago(7200), outcome: 'requested', action_ids: ['a1'] }] };

  it('lists rules, the trigger in words and the runs', async () => {
    await mount(<AutomationScreen />, base);
    expect(await screen.findByText('Nightly photo backup')).toBeTruthy();
    expect(screen.getByText(/on a schedule \(0 3 \* \* \*, box\)/)).toBeTruthy();
    expect(screen.getByText('requested, 1 request(s)')).toBeTruthy();
    expect(screen.getByText(/Rules can only ask/)).toBeTruthy();
  });

  it('turning a rule off is one tap', async () => {
    const setRuleEnabled = jest.fn(async () => rule({ enabled: false }));
    await mount(<AutomationScreen />, { ...base, setRuleEnabled });
    await fireEvent.press(await screen.findByTestId('disable-r1'));
    expect(await screen.findByText('Nightly photo backup is off.')).toBeTruthy();
    expect(setRuleEnabled).toHaveBeenCalledWith('r1', false);
  });

  it('turning a rule on takes two taps and says its requests still wait', async () => {
    const setRuleEnabled = jest.fn(async () => rule());
    await mount(<AutomationScreen />, { ...base, automationRules: async () => [rule({ enabled: false })], setRuleEnabled });
    await fireEvent.press(await screen.findByTestId('enable-r1'));
    expect(setRuleEnabled).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByText('Tap again: this rule may start asking'));
    expect(await screen.findByText(/Its requests still wait for approval/)).toBeTruthy();
    expect(setRuleEnabled).toHaveBeenCalledWith('r1', true);
  });

  it('pause is one tap; resume asks twice', async () => {
    const setAutomationPaused = jest.fn(async (paused: boolean) => ({ paused }));
    await mount(<AutomationScreen />, { ...base, setAutomationPaused });
    await fireEvent.press(await screen.findByTestId('pause'));
    expect(setAutomationPaused).toHaveBeenCalledWith(true, expect.any(String));
  });

  it('while paused, resume needs a second tap', async () => {
    const setAutomationPaused = jest.fn(async (paused: boolean) => ({ paused }));
    await mount(<AutomationScreen />, { ...base, automationState: async () => ({ paused: true, reason: 'away' }), setAutomationPaused });
    expect(await screen.findByText('Paused')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('resume'));
    expect(setAutomationPaused).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByText('Tap again: let rules fire again'));
    expect(setAutomationPaused).toHaveBeenCalledWith(false);
  });

  it('an adult sees the rules but cannot change them', async () => {
    await mount(<AutomationScreen />, { ...base, me: async () => ADULT_ME });
    expect(await screen.findByText('Nightly photo backup')).toBeTruthy();
    expect(screen.getByTestId('disable-r1')).toBeDisabled();
    expect(screen.getByText('Only an owner can change rules.')).toBeTruthy();
  });

  it('a 403 from the hub turns the buttons off', async () => {
    await mount(<AutomationScreen />, { ...base, setRuleEnabled: forbidden });
    await fireEvent.press(await screen.findByTestId('disable-r1'));
    expect(await screen.findByText(/may not do that change/)).toBeTruthy();
    expect(screen.getByTestId('disable-r1')).toBeDisabled();
  });

  it('describes triggers', () => {
    expect(triggerText({ trigger: { event: { type: 'backup.failed' } } })).toBe('when backup.failed happens');
    expect(triggerText({ trigger: {} })).toBe('unknown trigger');
  });
});

describe('Files screen', () => {
  it('browses a root and a folder, read only', async () => {
    const filesList = jest.fn(async (_root: string, path: string) =>
      path === '/'
        ? [
            { name: 'Photos', type: 'dir' },
            { name: 'notes.txt', type: 'file', size: 2048 },
          ]
        : [{ name: 'a.jpg', type: 'file', size: 3_000_000 }],
    );
    await mount(<FilesScreen />, { filesRoots: async () => [{ root: 'home:owner', kind: 'home', name: 'My files', path: '/', writable: true, used_bytes: 5_000_000, quota_bytes: null }], filesList });
    await fireEvent.press(await screen.findByTestId('root-home:owner'));
    expect(await screen.findByText('notes.txt')).toBeTruthy();
    expect(screen.getByText('2.0 KB')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('dir-Photos'));
    expect(await screen.findByText('a.jpg')).toBeTruthy();
    expect(filesList).toHaveBeenLastCalledWith('home:owner', '/Photos');
    await fireEvent.press(screen.getByTestId('files-up'));
    expect(await screen.findByText('notes.txt')).toBeTruthy();
  });

  it('says so when nothing is shared, and when the hub refuses', async () => {
    await mount(<FilesScreen />, { filesRoots: async () => [] });
    expect(await screen.findByText('No folders are shared with you.')).toBeTruthy();
  });

  it('a 403 on roots is a plain notice', async () => {
    await mount(<FilesScreen />, { filesRoots: forbidden });
    expect(await screen.findByText('This sign-in has no files.')).toBeTruthy();
  });

  it('path helpers', () => {
    expect(join('/', 'a')).toBe('/a');
    expect(join('/a/', 'b')).toBe('/a/b');
    expect(parentOf('/a/b')).toBe('/a');
    expect(parentOf('/a')).toBe('/');
  });
});

describe('Migration screen', () => {
  it('lists plans read only and explains why there is no copy button', async () => {
    await mount(<MigrateScreen />, { migratePlans: async () => [{ id: 'mp1', app_id: 'nextcloud', name: 'Nextcloud', namespace: 'old-ns', state: 'staged', last_error: null }] });
    expect(await screen.findByText('Nextcloud')).toBeTruthy();
    expect(screen.getByText('staged')).toBeTruthy();
    expect(screen.getByText(/kubeconfig. That is a credential/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('a non-owner (403) gets an owner-only notice', async () => {
    await mount(<MigrateScreen />, { migratePlans: forbidden });
    expect(await screen.findByText('Only an owner can see migration plans.')).toBeTruthy();
  });
});
