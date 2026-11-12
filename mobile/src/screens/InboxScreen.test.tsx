// SPDX-License-Identifier: Apache-2.0
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Text } from 'react-native';
import { Features, OP } from '../api/client';
import { makeAlerts } from '../api/fixtures';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { InboxScreen } from './InboxScreen';

const Stack = createNativeStackNavigator();

function deps(c: Connection, makeApi?: SessionDeps['makeApi']): SessionDeps {
  return { load: async () => c, save: async () => undefined, clear: async () => undefined, ...(makeApi ? { makeApi } : {}) };
}

/** Screens mount once the session has its features (as in the app after the first read). */
function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

function Approvals() {
  return <Text testID="approvals-tab">approvals</Text>;
}

async function renderInbox(d: SessionDeps, gate = true) {
  await render(
    <SessionProvider deps={d}>
      {gate ? (
        <Gate>
          <HubDataProvider intervalMs={0}>
            <NavigationContainer>
              <Stack.Navigator>
                <Stack.Screen name="Inbox" component={InboxScreen} />
                <Stack.Screen name="Tabs" component={Approvals} />
              </Stack.Navigator>
            </NavigationContainer>
          </HubDataProvider>
        </Gate>
      ) : null}
    </SessionProvider>,
  );
}

describe('Inbox screen', () => {
  it('shows open alerts and the owner\'s notifications, unread first-class, and marks all read', async () => {
    await renderInbox(deps({ mode: 'mock', token: 'owner-demo' }));
    expect(await screen.findByTestId('alert-alrt_demo_01')).toBeTruthy();
    expect(screen.getByTestId('ntf-ntf_demo_03')).toBeTruthy();
    expect(screen.getByTestId('unread-ntf_demo_01')).toBeTruthy();
    expect(screen.queryByTestId('unread-ntf_demo_03')).toBeNull();
    await fireEvent.press(screen.getByTestId('read-all'));
    await waitFor(() => expect(screen.queryByTestId('unread-ntf_demo_01')).toBeNull());
  });

  it('a fix is filed as a request for the owner to approve, never applied directly', async () => {
    await renderInbox(deps({ mode: 'mock', token: 'owner-demo' }));
    await fireEvent.press(await screen.findByTestId('fix-alrt_demo_02'));
    expect(await screen.findByText('Asked to fix: catalog.refresh. It waits in Approvals.')).toBeTruthy();
  });

  it('tapping a notification about a request opens Approvals', async () => {
    await renderInbox(deps({ mode: 'mock', token: 'owner-demo' }));
    await fireEvent.press(await screen.findByTestId('ntf-ntf_demo_01'));
    expect(await screen.findByTestId('approvals-tab')).toBeTruthy();
  });

  it('an adult sees only their own inbox and no fix button', async () => {
    await renderInbox(deps({ mode: 'mock', token: 'adult-demo' }));
    expect(await screen.findByTestId('ntf-ntf_demo_11')).toBeTruthy();
    expect(screen.queryByTestId('alert-alrt_demo_01')).toBeNull();
  });

  it('an adult who may request other things still gets no "Ask to fix" (§12.14: owner or agent), but may acknowledge', async () => {
    const api = v0Api({
      features: async () => new Features([OP.me, OP.alerts], 'openapi'),
      me: async () => ({
        principal: { id: 'person:adult1', kind: 'person', role: 'adult' },
        token: null,
        session: { id: 'ses_1', expires_at: '2030-01-01T00:00:00Z' },
        passkeys: 1,
        capabilities: ['can_request'],
      }),
      alerts: async () => makeAlerts(Date.now()),
    });
    await renderInbox(deps({ mode: 'live', hubUrl: 'https://hub.example', token: 't' }, () => api));
    expect(await screen.findByTestId('alert-alrt_demo_02')).toBeTruthy();
    expect(screen.queryByTestId('fix-alrt_demo_02')).toBeNull();
    expect(screen.getByTestId('ack-alrt_demo_02')).toBeTruthy();
  });

  it('says plainly when the hub has no inbox yet', async () => {
    const api = v0Api({ features: async () => new Features([], 'openapi') });
    await renderInbox(deps({ mode: 'live', hubUrl: 'https://hub.example', token: 't' }, () => api));
    expect(await screen.findByText(/This hub has no inbox yet/)).toBeTruthy();
  });
});
