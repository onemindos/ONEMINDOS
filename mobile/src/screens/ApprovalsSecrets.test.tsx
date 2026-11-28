// SPDX-License-Identifier: Apache-2.0
// #528: approving an install whose app needs owner-typed secrets opens a form on the phone; the values
// are sealed here to the box key and travel only inside the signed approval.
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { AccessibilityInfo } from 'react-native';
import { Passkey } from 'react-native-passkey';
import { Features, OP } from '../api/client';
import { makeActions } from '../api/fixtures';
import type { Action, AppSecrets, ApproveBody } from '../api/types';
import { HubDataProvider } from '../data';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import { testBox } from '../test/expoCryptoWeb';
import { v0Api } from '../test/fakes';
import { mockConnection } from '../test/mockHub';
import { ApprovalsScreen } from './ApprovalsScreen';

jest.mock('expo-crypto', () => jest.requireActual('../test/expoCryptoWeb').expoCryptoWeb());

const SECRETS: AppSecrets = {
  app_id: 'ollama', key_id: 'sk_test', missing_required: ['ollama-auth/API_KEY'],
  secrets: [{ name: 'ollama-auth', description: 'Auth', keys: [
    { key: 'API_KEY', kind: 'api-key', description: 'Provider key', required: true, source: 'owner', set: false, version: null, updated_at: null },
    { key: 'SESSION', kind: 'token', description: '', required: false, source: 'generated', set: false, version: null, updated_at: null },
  ] }],
};
const owner = { principal: { id: 'owner', kind: 'person' as const, role: 'owner' as const }, capabilities: ['can_approve'], token: null, session: null, passkeys: 1 };
const signed = { id: 'credential', response: { clientDataJSON: 'client', authenticatorData: 'auth', signature: 'sig' } };

function Gate({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

beforeEach(() => {
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
  jest.mocked(Passkey.isSupported).mockReturnValue(true);
  jest.mocked(Passkey.get).mockResolvedValue(signed as Awaited<ReturnType<typeof Passkey.get>>);
});
afterEach(() => {
  jest.restoreAllMocks();
  jest.mocked(Passkey.isSupported).mockReturnValue(false);
  jest.mocked(Passkey.get).mockReset();
});

async function setup(opts: { secrets?: AppSecrets; features?: string[]; extra?: Action[]; intervalMs?: number } = {}) {
  const box = await testBox();
  const a = makeActions(Date.now())[0]!;
  const action = { ...a, expires_at: new Date(Date.now() + 600_000).toISOString() };
  const calls: Array<ApproveBody | undefined> = [];
  const list = { current: [action, ...(opts.extra ?? [])] };
  const approve = jest.fn(async (id: string, body?: ApproveBody) => { calls.push(body); return { ...list.current.find((x) => x.id === id)!, state: 'accepted' as const }; });
  const api = v0Api({
    features: async () => new Features(opts.features ?? [OP.me, OP.approveOptions, OP.appSecrets, OP.secretsPublicKey], 'openapi'),
    me: async () => owner,
    actions: async () => list.current,
    approveOptions: async () => ({ challenge: 'c', plan_sha256: action.plan_sha256 ?? null, action_sha256: 'sha256:a', expires_at: action.expires_at }),
    approve,
    appSecrets: jest.fn(async () => opts.secrets ?? SECRETS),
    secretsPublicKey: jest.fn(async () => box.publicKey),
  });
  const deps: SessionDeps = { load: async () => mockConnection('owner-demo'), save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}><Gate><HubDataProvider intervalMs={opts.intervalMs ?? 0}><ApprovalsScreen /></HubDataProvider></Gate></SessionProvider>,
  );
  await screen.findByTestId('pending-act-0001');
  return { box, approve, calls, action, list };
}

describe('Approvals screen: install secrets (#528)', () => {
  it('asks for the owner-typed secret, refuses an empty form, then seals it into the signed approval', async () => {
    const { box, approve, calls, action } = await setup();
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByTestId('secrets-ollama')).toBeTruthy();
    expect(screen.getByText('One more key is made by the box itself.')).toBeTruthy();
    expect(approve).not.toHaveBeenCalled();
    // The field is masked until the owner asks to see it.
    expect(screen.getByTestId('secret-ollama-auth/API_KEY').props.secureTextEntry).toBe(true);

    await fireEvent.press(screen.getByTestId('secrets-submit-ollama'));
    expect(screen.getByTestId('problem-ollama-auth/API_KEY')).toHaveTextContent('Required to install.');
    expect(approve).not.toHaveBeenCalled();

    const value = 'sk-live-' + Math.random().toString(36).slice(2);
    await fireEvent.changeText(screen.getByTestId('secret-ollama-auth/API_KEY'), value);
    await fireEvent.press(screen.getByTestId('secrets-submit-ollama'));
    expect(await screen.findByText(/Approved.*Install ollama/)).toBeTruthy();
    expect(approve).toHaveBeenCalledTimes(1);
    const body = calls[0]!;
    expect(body).toMatchObject({ plan_sha256: action.plan_sha256, webauthn: expect.objectContaining({ signature: 'sig' }), sealed: { alg: 'X25519-AES256GCM', kid: 'sk_test' } });
    // Never in clear on the wire: only the box key opens it, and only for this app.
    expect(JSON.stringify(body)).not.toContain(value);
    expect(JSON.parse(await box.open(body!.sealed!, 'onemind/app-secrets/ollama'))).toEqual({ values: { 'ollama-auth': { API_KEY: value } } });
    expect(screen.queryByTestId('secrets-ollama')).toBeNull();
  });

  it('the request behind an open form is decided elsewhere: the form closes and the other cards work again', async () => {
    const other: Action = { ...makeActions(Date.now())[0]!, id: 'act-0009', type: 'app.start', risk: 'write', plan: undefined, plan_sha256: undefined,
      created_at: new Date(Date.now() - 600_000).toISOString(), updated_at: new Date(Date.now() - 600_000).toISOString(),
      expires_at: new Date(Date.now() + 600_000).toISOString() };
    const { approve, list } = await setup({ extra: [other], intervalMs: 50 });
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByTestId('secrets-ollama')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('expand-act-0009'));
    expect(screen.getByTestId('approve-act-0009')).toBeDisabled();
    // Approved on the dashboard meanwhile: the next reload no longer lists it as waiting.
    list.current = [{ ...list.current[0]!, state: 'succeeded' }, other];
    await waitFor(() => expect(screen.queryByTestId('secrets-ollama')).toBeNull());
    await waitFor(() => expect(screen.getByTestId('approve-act-0009')).not.toBeDisabled());
    await fireEvent.press(screen.getByTestId('approve-act-0009'));
    await waitFor(() => expect(approve).toHaveBeenCalledWith('act-0009', expect.not.objectContaining({ sealed: expect.anything() })));
  });

  it('Cancel closes the form and approves nothing', async () => {
    const { approve } = await setup();
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    await fireEvent.changeText(await screen.findByTestId('secret-ollama-auth/API_KEY'), 'sk-abcdef');
    await fireEvent.press(screen.getByTestId('secrets-cancel-ollama'));
    expect(screen.queryByTestId('secrets-ollama')).toBeNull();
    expect(approve).not.toHaveBeenCalled();
  });

  it('an app with only box-made keys, or a hub without sealing, approves with no form and no sealed field', async () => {
    const generatedOnly = { ...SECRETS, secrets: [{ ...SECRETS.secrets[0]!, keys: [SECRETS.secrets[0]!.keys[1]!] }] };
    const { calls } = await setup({ secrets: generatedOnly });
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByText(/Approved.*Install ollama/)).toBeTruthy();
    expect(screen.queryByTestId('secrets-ollama')).toBeNull();
    expect(calls[0]).not.toHaveProperty('sealed');
  });
});
