// SPDX-License-Identifier: Apache-2.0
// Activity against a fake gateway. The current gateway puts the approval card object (#723) in an
// action's `approval`, where a §12.4 hub sent a string; the screen must show one and not crash on the other
// (contract.ts found the drift, CI-08 #233).
import { NavigationContainer } from '@react-navigation/native';
import { render, screen } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Features } from '../api/client';
import { makeActions } from '../api/fixtures';
import type { Action } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { ActivityScreen } from './ActivityScreen';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(actions: Action[]) {
  const api = v0Api({ features: async () => new Features([], 'openapi'), actions: async () => actions });
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <HubDataProvider intervalMs={0}>
          <NavigationContainer>
            <ActivityScreen />
          </NavigationContainer>
        </HubDataProvider>
      </Gate>
    </SessionProvider>,
  );
}

it('lists an action whose approval is the gateway approval card, without a method row', async () => {
  const base = makeActions(Date.now())[0]!;
  await mount([{ ...base, id: 'act-card', state: 'succeeded', approval: { hold: false, physical: false } }]);
  expect(await screen.findByText('act-card')).toBeTruthy();
  expect(screen.queryByText('Approved')).toBeNull();
});

it('still labels how a §12.4 hub says the yes was given', async () => {
  const base = makeActions(Date.now())[0]!;
  await mount([{ ...base, id: 'act-token', state: 'succeeded', approval: 'token' }]);
  expect(await screen.findByText('without a passkey')).toBeTruthy();
});
