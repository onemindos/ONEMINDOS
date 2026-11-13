// SPDX-License-Identifier: Apache-2.0
import { NavigationContainer } from '@react-navigation/native';
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Features, OP } from '../api/client';
import { makeApps } from '../api/fixtures';
import { ApiError, type CatalogApp } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { AppLifecycle } from './AppLifecycle';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const kuma = (over: Partial<CatalogApp> = {}): CatalogApp => ({ ...makeApps().find((a) => a.id === 'uptime-kuma')!, ...over });
const PLAN = {
  app_id: 'uptime-kuma',
  policy_verdict: 'needs_approval',
  risk: 'write' as const,
  plan: { summary: 'Restart Uptime Kuma. It is down for about a minute.', warnings: ['Open sessions are dropped.'], volumes: [{}] },
  plan_sha256: 'sha256:plan1',
};

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(app: CatalogApp, over: Parameters<typeof v0Api>[0] = {}, conn: Connection = LIVE) {
  const api = v0Api({
    features: async () => new Features([OP.appPlan, OP.me], 'openapi'),
    appPlan: async () => PLAN,
    actions: async () => [],
    ...over,
  });
  const deps: SessionDeps = { load: async () => conn, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <HubDataProvider intervalMs={0}>
          <NavigationContainer>
            <AppLifecycle app={app} />
          </NavigationContainer>
        </HubDataProvider>
      </Gate>
    </SessionProvider>,
  );
  return api;
}

describe('AppLifecycle', () => {
  it('shows the plan first, and only then files the request, bound to the plan hash', async () => {
    const createAction = jest.fn(async (r) => ({ ...r, id: 'act-77', state: 'awaiting_approval' as const }));
    await mount(kuma(), { createAction });
    await fireEvent.press(await screen.findByTestId('lifecycle-app.restart'));
    expect(await screen.findByText(/Restart Uptime Kuma. It is down for about a minute./)).toBeTruthy();
    expect(screen.getByText('Open sessions are dropped.')).toBeTruthy();
    expect(createAction).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId('lifecycle-send'));
    expect(await screen.findByText(/waits in Approvals until an owner decides/)).toBeTruthy();
    expect(screen.getByText('awaiting approval')).toBeTruthy();
    expect(createAction).toHaveBeenCalledWith(expect.objectContaining({ type: 'app.restart', params: { app_id: 'uptime-kuma' }, plan_sha256: 'sha256:plan1' }));
  });

  it('cancelling the plan sends nothing', async () => {
    const createAction = jest.fn();
    await mount(kuma(), { createAction });
    await fireEvent.press(await screen.findByTestId('lifecycle-app.stop'));
    await fireEvent.press(await screen.findByTestId('lifecycle-cancel'));
    expect(screen.queryByTestId('lifecycle-plan')).toBeNull();
    expect(createAction).not.toHaveBeenCalled();
  });

  it('a stopped app offers start, not stop', async () => {
    await mount(kuma({ status: 'stopped' }));
    expect(await screen.findByTestId('lifecycle-app.start')).toBeTruthy();
    expect(screen.queryByTestId('lifecycle-app.stop')).toBeNull();
  });

  it('an app that is updating offers nothing', async () => {
    await mount(kuma({ status: 'updating' }));
    expect(await screen.findByText(/actions are available when it settles/)).toBeTruthy();
    expect(screen.queryByTestId('lifecycle-app.restart')).toBeNull();
  });

  it('a plan the hub refuses is not offered for sending', async () => {
    await mount(kuma(), { appPlan: async () => ({ ...PLAN, policy_verdict: 'refused', reason: 'already stopped' }) });
    await fireEvent.press(await screen.findByTestId('lifecycle-app.stop'));
    expect(await screen.findByText(/will not file this now: already stopped/)).toBeTruthy();
    expect(screen.queryByTestId('lifecycle-send')).toBeNull();
  });

  it('a changed plan (409 plan_changed) is explained and nothing is claimed', async () => {
    const createAction = jest.fn(async () => {
      throw new ApiError(409, 'stale_precondition', 'plan differs', { reason: 'plan_changed' });
    });
    await mount(kuma(), { createAction });
    await fireEvent.press(await screen.findByTestId('lifecycle-app.update'));
    await fireEvent.press(await screen.findByTestId('lifecycle-send'));
    expect(await screen.findByText(/plan for the update changed/)).toBeTruthy();
    expect(screen.queryByText(/Request sent/)).toBeNull();
  });

  it('a 403 on the request says only an owner can', async () => {
    const createAction = jest.fn(async () => {
      throw new ApiError(403, 'permission_denied', 'owner only');
    });
    await mount(kuma(), { createAction });
    await fireEvent.press(await screen.findByTestId('lifecycle-app.restart'));
    await fireEvent.press(await screen.findByTestId('lifecycle-send'));
    expect(await screen.findByText(/Only an owner can/)).toBeTruthy();
  });

  it('is disabled with a plain reason for someone who cannot request (an adult)', async () => {
    const me = { principal: { id: 'alex', kind: 'person' as const, role: 'adult' as const }, token: null, session: null, passkeys: 0, capabilities: [] };
    await mount(kuma(), { me: async () => me });
    expect(await screen.findByText(/Only an owner \(or an agent\) can ask for changes/)).toBeTruthy();
    expect(screen.getByTestId('lifecycle-app.restart')).toBeDisabled();
  });

  it('renders nothing without the plan route', async () => {
    await mount(kuma(), { features: async () => new Features([OP.me], 'openapi') });
    expect(screen.queryByTestId('lifecycle-app.restart')).toBeNull();
  });
});
