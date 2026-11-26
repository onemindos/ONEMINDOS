// SPDX-License-Identifier: Apache-2.0
// People, Agents and "Ask a parent" against a fake gateway; each screen's entry hides when the hub lacks the route.
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactElement, ReactNode } from 'react';
import { Features, OP } from '../api/client';
import { makeApps } from '../api/fixtures';
import { ApiError, type Action, type UserInfo } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { AgentsScreen } from './AgentsScreen';
import { AppDetailScreen } from './AppDetailScreen';
import { MoreScreen } from './MoreScreen';
import { PeopleScreen } from './PeopleScreen';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const me = (role: 'owner' | 'adult' | 'teen' | 'child', caps: string[] = []) => ({ principal: { id: `${role}1`, kind: 'person' as const, role }, token: null, session: null, passkeys: 0, capabilities: caps });
const OWNER = me('owner', ['can_approve', 'can_request']);
const OWNER_OPS = [OP.me, OP.users, OP.usersCreate, OP.usersUpdate, OP.familyProfile, OP.tokens, OP.killSwitch, OP.killSwitchSet];
const USERS: UserInfo[] = [
  { id: 'u1', username: 'zeus', display_name: 'Zeus', role: 'owner' },
  { id: 'u2', username: null, display_name: 'Mia', role: 'teen' },
  { id: 'u3', username: null, display_name: 'Leo', role: 'child' },
  { id: 'u4', username: null, display_name: 'Gus', role: 'guest' },
];

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}
async function mount(ui: ReactElement, ops: string[], over: Parameters<typeof v0Api>[0] = {}) {
  const api = v0Api({ features: async () => new Features(ops, 'openapi'), me: async () => OWNER, actions: async () => [], ...over });
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

describe('More hides People and Agents without their routes', () => {
  it('shows neither on a hub without them', async () => {
    await mount(<MoreScreen />, [OP.me]);
    expect(await screen.findByTestId('more-Nodes')).toBeTruthy();
    expect(screen.queryByTestId('more-People')).toBeNull();
    expect(screen.queryByTestId('more-Agents')).toBeNull();
  });
  it('shows both when the hub serves them', async () => {
    await mount(<MoreScreen />, OWNER_OPS);
    expect(await screen.findByTestId('more-People')).toBeTruthy();
    expect(screen.getByTestId('more-Agents')).toBeTruthy();
  });
});

describe('People screen', () => {
  const base = { users: async () => USERS, familyProfile: async () => ({ max_age_rating: 12, allowed_apps: ['a'] }) };

  it('lists the roles and the limits of a teen and a child', async () => {
    await mount(<PeopleScreen />, OWNER_OPS, base);
    expect(await screen.findByTestId('person-u2')).toBeTruthy();
    expect(screen.getAllByText('Teen').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Child').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Guest').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/apps rated above 12 are hidden; 1 allowed app\./).length).toBe(2);
  });

  it('changes a role only on the second tap, and the hub does it', async () => {
    const setUserRole = jest.fn(async (id: string, role: string) => ({ ...USERS[3]!, id, role }));
    await mount(<PeopleScreen />, OWNER_OPS, { ...base, setUserRole });
    await fireEvent.press(await screen.findByTestId('role-u4-adult'));
    await fireEvent.press(screen.getByTestId('role-save-u4'));
    expect(setUserRole).not.toHaveBeenCalled();
    expect(screen.getByText(/Tap again: make Gus Adult/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId('role-save-u4'));
    expect(setUserRole).toHaveBeenCalledWith('u4', 'adult');
    expect(await screen.findByText('Gus is now Adult.')).toBeTruthy();
  });

  it('says to sign in again with a passkey when the hub asks for step-up', async () => {
    const createUser = jest.fn(async () => {
      throw new ApiError(401, 'unauthenticated', 'passkey', { reason: 'step_up_required' });
    });
    await mount(<PeopleScreen />, OWNER_OPS, { ...base, createUser });
    await fireEvent.changeText(await screen.findByTestId('new-name'), 'Ana');
    await fireEvent.press(screen.getByTestId('new-role-teen'));
    await fireEvent.press(screen.getByTestId('add'));
    await fireEvent.press(screen.getByTestId('add'));
    expect(createUser).toHaveBeenCalledWith({ display_name: 'Ana', role: 'teen' });
    expect(await screen.findByText(/your passkey before .* Nothing was changed/)).toBeTruthy();
  });

  it('shows the one-time sign-in link after adding a person, then drops it', async () => {
    const createUser = jest.fn(async () => ({ id: 'u9', username: null, display_name: 'Ana', role: 'teen', one_time: { enrolment_code: 'CODE123', enrolment_url: 'https://hub/signin#enrol=CODE123' } }));
    await mount(<PeopleScreen />, OWNER_OPS, { ...base, createUser });
    await fireEvent.changeText(await screen.findByTestId('new-name'), 'Ana');
    await fireEvent.press(screen.getByTestId('add'));
    await fireEvent.press(screen.getByTestId('add'));
    expect(await screen.findByText('https://hub/signin#enrol=CODE123')).toBeTruthy();
    expect(screen.getByText('Code: CODE123')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('invite-done'));
    expect(screen.queryByTestId('invite')).toBeNull();
  });

  it('offers no writes to an adult', async () => {
    await mount(<PeopleScreen />, OWNER_OPS, { ...base, me: async () => me('adult'), users: async () => { throw new ApiError(403, 'permission_denied', 'no'); } });
    expect(await screen.findByText('Only an owner can see people.')).toBeTruthy();
    expect(screen.queryByTestId('add')).toBeNull();
  });
});

describe('Agents screen', () => {
  const asks: Action[] = [
    { id: 'a1', type: 'app.install', params: { app_id: 'jellyfin' }, idempotency_key: 'k', expires_at: '', state: 'awaiting_approval', created_at: new Date().toISOString(), requested_by: { id: 'agent:hermes', kind: 'agent' } },
  ];
  const base = {
    actions: async () => asks,
    killSwitch: async () => ({ on: false }),
    apiTokens: async () => [{ id: 't', name: 'Hermes', principal_id: 'agent:hermes', kind: 'agent', scopes: ['apps:read'] }],
  };

  it('shows each agent with scopes and recent asks', async () => {
    await mount(<AgentsScreen />, OWNER_OPS, base);
    expect(await screen.findByTestId('agent-agent:hermes')).toBeTruthy();
    expect(screen.getByText('1 waiting')).toBeTruthy();
    expect(screen.getByText('May: apps:read')).toBeTruthy();
    expect(screen.getByText('app.install jellyfin')).toBeTruthy();
  });

  it('stops every agent only on the second tap', async () => {
    const setKillSwitch = jest.fn(async (on: boolean) => ({ on }));
    await mount(<AgentsScreen />, OWNER_OPS, { ...base, setKillSwitch });
    await fireEvent.press(await screen.findByTestId('kill-switch-toggle'));
    expect(setKillSwitch).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByTestId('kill-switch-toggle'));
    expect(setKillSwitch).toHaveBeenCalledWith(true, 'Stopped from the phone');
    expect(await screen.findByText('Every agent is stopped.')).toBeTruthy();
  });

  it('turns agents back on in one tap and relays a step-up need', async () => {
    const setKillSwitch = jest.fn(async () => {
      throw new ApiError(401, 'unauthenticated', 'passkey', { reason: 'step_up_required' });
    });
    await mount(<AgentsScreen />, OWNER_OPS, { ...base, killSwitch: async () => ({ on: true }), setKillSwitch });
    await fireEvent.press(await screen.findByTestId('kill-switch-toggle'));
    expect(setKillSwitch).toHaveBeenCalledWith(false, undefined);
    expect(await screen.findByText(/wants your passkey/)).toBeTruthy();
  });

  it('shows the error, no badge and no toggle when the kill switch cannot be read', async () => {
    await mount(<AgentsScreen />, OWNER_OPS, { ...base, killSwitch: async () => { throw new ApiError(500, 'unknown', 'boom'); } });
    expect(await screen.findByText(/cannot say whether agents are stopped/)).toBeTruthy();
    expect(screen.queryByText('Agents allowed to ask')).toBeNull();
    expect(screen.queryByTestId('kill-switch-toggle')).toBeNull();
  });

  it('says the route is missing when the hub does not serve it', async () => {
    await mount(<AgentsScreen />, [OP.me], { ...base, killSwitch: async () => { throw new ApiError(404, 'not_found', 'no'); } });
    expect(await screen.findByText(/does not serve the agent kill switch/)).toBeTruthy();
    expect(screen.queryByText('Agents allowed to ask')).toBeNull();
  });

  it('gives an adult no switch', async () => {
    await mount(<AgentsScreen />, OWNER_OPS, { ...base, me: async () => me('adult') });
    expect(await screen.findByText('Only an owner can stop or restart agents.')).toBeTruthy();
    expect(screen.queryByTestId('kill-switch-toggle')).toBeNull();
  });
});

describe('Ask a parent', () => {
  const appId = makeApps(Date.now()).find((a) => !a.installed && a.scan?.result === 'pass')!.id;
  const Stack = createNativeStackNavigator();
  const Detail = () => (
    <Stack.Navigator>
      <Stack.Screen name="AppDetail" component={AppDetailScreen} initialParams={{ id: appId }} />
    </Stack.Navigator>
  );

  it('offers no Ask a parent button for a teen: no hub route exists for it', async () => {
    const createAction = jest.fn();
    await mount(<Detail />, [OP.me], { me: async () => me('teen'), createAction });
    expect(await screen.findByText(/cannot file requests yet/)).toBeTruthy();
    expect(screen.queryByText('Ask a parent')).toBeNull();
    expect(createAction).not.toHaveBeenCalled();
  });
});
