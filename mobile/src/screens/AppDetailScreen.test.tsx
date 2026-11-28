// SPDX-License-Identifier: Apache-2.0
import { NavigationContainer } from '@react-navigation/native';
import { act, fireEvent, render, screen, within } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Passkey } from 'react-native-passkey';
import { Features, OP, type OneMindApi } from '../api/client';
import { makeActions, makeApps } from '../api/fixtures';
import type { Action } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession } from '../session';
import { v0Api } from '../test/fakes';
import { AppDetailScreen } from './AppDetailScreen';

jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useRoute: () => ({ params: { id: 'ollama' } }),
}));

function SignedIn({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

const action = () => ({
  ...makeActions(Date.now())[0]!,
  requested_by: { id: 'owner', kind: 'person' as const },
});

async function mount(current: Action, overrides: Partial<OneMindApi> = {}, role: 'owner' | 'adult' = 'owner', sparse = false) {
  const app = makeApps(Date.now()).find((a) => a.id === 'ollama')!;
  const api = v0Api({
    features: async () => new Features([OP.me, OP.appPlan, OP.approveOptions], 'openapi'),
    me: async () => ({
      principal: { id: role, kind: 'person', role }, capabilities: role === 'owner' ? ['can_approve'] : [],
      passkeys: 1, token: null, session: null,
    }),
    actions: async () => [current],
    apps: async () => [sparse ? { ...app, license: '', scan: null, web_port: null } : app],
    ...overrides,
  });
  await render(
    <SessionProvider deps={{
      load: async () => ({ mode: 'live', hubUrl: 'https://hub.example', token: 'test-token' }),
      save: async () => undefined, clear: async () => undefined, makeApi: () => api,
    }}>
      <SignedIn>
        <HubDataProvider intervalMs={0}>
          <NavigationContainer><AppDetailScreen /></NavigationContainer>
        </HubDataProvider>
      </SignedIn>
    </SessionProvider>,
  );
  return screen.findByTestId('app-install-waiting');
}

it.each([
  [{ kind: 'person', id: 'owner' }, 'Cancel request', 'Request cancelled'],
  [{ kind: 'agent', id: 'agent' }, 'Deny', 'Request denied'],
  [{ kind: 'person', id: 'another-owner' }, 'Deny', 'Request denied'],
] as const)('labels a request from %j and waits for the hub result', async (requester, button, outcome) => {
  const current = { ...action(), requested_by: requester };
  let resolve!: (value: Action) => void;
  const deny = jest.fn(() => new Promise<Action>((done) => { resolve = done; }));
  const card = await mount(current, { deny });
  for (const step of ['Asked', 'Checked', 'You', 'Install']) expect(card).toHaveTextContent(new RegExp(step));
  expect(within(card).getByRole('button', { name: button })).toBeEnabled();
  await fireEvent.press(screen.getByTestId('app-deny'));
  await fireEvent.press(screen.getByTestId('app-deny'));
  expect(deny).toHaveBeenCalledTimes(1);
  expect(deny).toHaveBeenCalledWith(current.id, undefined);
  expect(screen.getByTestId('app-install-waiting')).toBeTruthy();
  expect(screen.queryByTestId('app-decision-result')).toBeNull();
  await act(async () => { resolve({ ...current, state: 'cancelled' }); });
  expect(screen.queryByTestId('app-install-waiting')).toBeNull();
  expect(screen.getByTestId('app-decision-result')).toHaveTextContent(new RegExp(outcome));
  expect(screen.getByTestId('app-decision-result')).toHaveTextContent(/cancelled/);
});

it('shows the waiting state to a non-owner and omits facts the hub did not supply', async () => {
  const card = await mount(action(), {}, 'adult', true);
  expect(within(card).queryAllByRole('button')).toHaveLength(0);
  expect(screen.queryByTestId('app-trust')).toBeNull();
  expect(screen.queryByTestId('app-access')).toBeNull();
  expect(screen.queryByText('Size')).toBeNull();
});

it('signs the exact waiting plan after one tap', async () => {
  const current = action();
  const supported = jest.mocked(Passkey.isSupported).mockReturnValue(true);
  const get = jest.mocked(Passkey.get).mockResolvedValue({
    id: 'credential', response: { clientDataJSON: 'client', authenticatorData: 'auth', signature: 'sig' },
  } as Awaited<ReturnType<typeof Passkey.get>>);
  try {
    const approve = jest.fn(async () => ({ ...current, state: 'accepted' as const }));
    const approveOptions = jest.fn(async () => ({
      challenge: 'challenge', plan_sha256: current.plan_sha256!, action_sha256: 'sha256:a', expires_at: current.expires_at,
    }));
    const appPlan = jest.fn(async () => ({
      app_id: 'ollama', policy_verdict: 'needs_approval', plan: { summary: 'Different plan' }, plan_sha256: 'other',
    }));
    const card = await mount(current, { approveOptions, approve, appPlan });
    await fireEvent.press(within(card).getByRole('button', { name: 'Review plan' }));
    expect(await screen.findByTestId('app-review-plan-content')).toHaveTextContent(/Install Ollama/);
    expect(screen.queryByText('Different plan')).toBeNull();
    await fireEvent.press(screen.getByTestId('app-approve'));
    expect(approveOptions).toHaveBeenCalledWith(current.id);
    expect(approve).toHaveBeenCalledTimes(1);
    expect(approve).toHaveBeenCalledWith(current.id, {
      plan_sha256: current.plan_sha256,
      webauthn: { id: 'credential', clientDataJSON: 'client', authenticatorData: 'auth', signature: 'sig' },
    });
  } finally {
    supported.mockReturnValue(false);
    get.mockReset();
  }
});

it('reserves high-risk updates for the Approvals screen', async () => {
  await mount({ ...action(), type: 'app.update', risk: 'destructive' });
  expect(screen.getByTestId('app-install-waiting')).toHaveTextContent(/Update/);
  expect(screen.queryByTestId('app-approve')).toBeNull();
  expect(screen.getByText(/hold to approve/)).toBeTruthy();
  expect(screen.getByTestId('app-deny')).toBeEnabled();
});
