// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react-native';
import { ApiError } from '../api/types';
import { v0Api } from '../test/fakes';
import { HubDataProvider } from '../data';
import type { ReactNode } from 'react';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { ApprovalsScreen } from './ApprovalsScreen';
import { Features, OP } from '../api/client';
import { signingPayload } from '../approvalKey';
import { fakeKey } from '../approvalKey/testKey';
import type { ApprovalKeyNative } from '../../modules/onemind-approval-key';

function deps(c: Connection, makeApi?: SessionDeps['makeApi']): SessionDeps {
  return { load: async () => c, save: async () => undefined, clear: async () => undefined, ...(makeApi ? { makeApi } : {}) };
}

/** Like the app's Root: screens mount only once the stored connection is loaded. */
function Gate({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

async function renderApprovals(d: SessionDeps, keyNative?: ApprovalKeyNative) {
  await render(
    <SessionProvider deps={d}>
      <Gate>
        <HubDataProvider intervalMs={0}>
          <ApprovalsScreen keyNative={keyNative} />
        </HubDataProvider>
      </Gate>
    </SessionProvider>,
  );
  return screen.findByTestId('pending-act-0001');
}

describe('Approvals screen', () => {
  it('shows the exact request and the agent requester, and the owner approves it', async () => {
    await renderApprovals(deps({ mode: 'mock', token: 'owner-demo' }));
    const params = screen.getByTestId('params-act-0001');
    expect(params).toHaveTextContent(/"type": "app.install"/);
    expect(params).toHaveTextContent(/"app_id": "ollama"/);
    expect(screen.getByText('agent: ops-agent')).toBeTruthy();
    expect(screen.getByText(/cannot approve its own request/)).toBeTruthy();

    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByText('Approved (without a passkey) and done: Install ollama.')).toBeTruthy();
    expect(screen.queryByTestId('pending-act-0001')).toBeNull();
    expect(screen.getByText('Nothing is waiting.')).toBeTruthy();
  });

  it('the owner denies', async () => {
    await renderApprovals(deps({ mode: 'mock', token: 'owner-demo' }));
    await fireEvent.press(screen.getByTestId('deny-act-0001'));
    expect(await screen.findByText('Denied: Install ollama.')).toBeTruthy();
  });

  it('an adult sees the request but the buttons are off', async () => {
    await renderApprovals(deps({ mode: 'mock', token: 'adult-demo' }));
    expect(screen.getByText(/only an owner can approve or deny/)).toBeTruthy();
    expect(screen.getByTestId('approve-act-0001')).toBeDisabled();
    expect(screen.getByTestId('deny-act-0001')).toBeDisabled();
  });

  it('against a live hub the role is unknown until the hub answers 403; then the buttons turn off', async () => {
    const approve = jest.fn(async () => {
      throw new ApiError(403, 'permission_denied', 'owner only');
    });
    const api = v0Api({ approve, deny: approve });
    await renderApprovals(deps({ mode: 'live', hubUrl: 'https://hub.example', token: 't' }, () => api));
    expect(screen.getByText(/checks that you are an owner/)).toBeTruthy();
    expect(screen.getByTestId('approve-act-0001')).toBeEnabled();
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByText(/This token is not an owner/)).toBeTruthy();
    expect(approve).toHaveBeenCalledWith('act-0001');
    expect(screen.getByTestId('approve-act-0001')).toBeDisabled();
  });
});

describe('Approvals screen: approval key (#703)', () => {
  it('an owner sets up the key, then approving signs the plan inside the biometric prompt', async () => {
    const k = fakeKey();
    k.native.status.mockReturnValue({ biometrics: 'ok', strongBoxAvailable: true, publicKey: null as unknown as string });
    const approverKeyRegister = jest.fn(async () => ({ key_id: 'ak_1', label: 'Android phone', key_kind: 'hardware-reported', fingerprint: 'sha256:f', created_at: '', last_used_at: null, revoked_at: null }));
    const approve = jest.fn(async (id: string) => ({ id, type: 'app.install', params: { app_id: 'ollama' }, state: 'accepted' }) as never);
    const approveOptions = jest.fn(async (id: string) => {
      const o = { challenge: `c-${approveOptions.mock.calls.length}`, action_sha256: 'sha256:a', plan_sha256: null, expires_at: '2030-01-01T00:00:00Z' };
      return { ...o, device_payload: signingPayload(o.challenge, id, o.action_sha256, null) };
    });
    const api = v0Api({
      features: async () => new Features([OP.approveOptions, OP.approverKeys], 'openapi'),
      approverKeyRegister,
      approveOptions,
      approve,
    });
    await renderApprovals(deps({ mode: 'live', hubUrl: 'https://hub.example', token: 't' }, () => api), k.native);
    await fireEvent.press(await screen.findByTestId('approval-key-setup'));
    expect(await screen.findByText(/Approval key set up/)).toBeTruthy();
    expect(approverKeyRegister).toHaveBeenCalledWith({ public_key: k.spki, label: 'Android phone', key_kind: 'hardware-reported' });
    expect(screen.getByText(/A PIN is not accepted/)).toBeTruthy();

    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByText(/with this phone's approval key/)).toBeTruthy();
    expect(k.native.sign).toHaveBeenCalledWith(expect.stringMatching(/^onemind-approve-v1\nact-0001\n/), 'Approve: Install ollama', expect.any(String));
    expect((approve.mock.calls[0] as unknown[])[1]).toMatchObject({ device_signature: { key_id: 'ak_1' } });
  });

  it('a new fingerprint kills the key: the approval is refused and set-up is offered again', async () => {
    const k = fakeKey();
    k.native.sign.mockRejectedValueOnce(Object.assign(new Error('new enrolment'), { code: 'ERR_KEY_INVALIDATED' }));
    const approverKeyRegister = jest.fn(async () => ({ key_id: 'ak_2', label: 'p', key_kind: 'hardware-reported', fingerprint: 'f', created_at: '', last_used_at: null, revoked_at: null }));
    const approverKeyRevoke = jest.fn(async () => undefined);
    const approve = jest.fn();
    const api = v0Api({
      features: async () => new Features([OP.approveOptions, OP.approverKeys], 'openapi'),
      approverKeyRegister,
      approverKeyRevoke,
      approve,
      approveOptions: async (id: string) => ({ challenge: 'z', action_sha256: 'sha256:a', plan_sha256: null, expires_at: '2030-01-01T00:00:00Z', device_payload: signingPayload('z', id, 'sha256:a', null) }),
    });
    await renderApprovals(deps({ mode: 'live', hubUrl: 'https://hub.example', token: 't' }, () => api), k.native);
    await fireEvent.press(await screen.findByTestId('approval-key-setup'));
    await screen.findByTestId('approval-key-remove');
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByText(/Set up the approval key again/)).toBeTruthy();
    expect(approve).not.toHaveBeenCalled();
    expect(approverKeyRevoke).toHaveBeenCalledWith('ak_2');
    expect(await screen.findByTestId('approval-key-setup')).toBeTruthy();
  });
});
