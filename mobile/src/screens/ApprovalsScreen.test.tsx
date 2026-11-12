// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { OneMindApi } from '../api/client';
import { makeActions, makeApps, makeNodes, INSTANCE } from '../api/fixtures';
import { ApiError } from '../api/types';
import { HubDataProvider } from '../data';
import type { ReactNode } from 'react';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { ApprovalsScreen } from './ApprovalsScreen';

function deps(c: Connection, makeApi?: SessionDeps['makeApi']): SessionDeps {
  return { load: async () => c, save: async () => undefined, clear: async () => undefined, ...(makeApi ? { makeApi } : {}) };
}

/** Like the app's Root: screens mount only once the stored connection is loaded. */
function Gate({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

async function renderApprovals(d: SessionDeps) {
  await render(
    <SessionProvider deps={d}>
      <Gate>
        <HubDataProvider intervalMs={0}>
          <ApprovalsScreen />
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
    expect(await screen.findByText('Approved and done: Install ollama.')).toBeTruthy();
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
    const now = Date.now();
    const approve = jest.fn(async () => {
      throw new ApiError(403, 'permission_denied', 'owner only');
    });
    const api: OneMindApi = {
      healthz: async () => ({ ok: true }),
      instance: async () => INSTANCE,
      nodes: async () => makeNodes(now),
      node: async () => makeNodes(now)[0]!,
      apps: async () => makeApps(now),
      actions: async () => makeActions(now),
      action: async () => makeActions(now)[0]!,
      createAction: async () => makeActions(now)[0]!,
      approve,
      deny: approve,
      hubOffsetMs: () => 0,
    };
    await renderApprovals(deps({ mode: 'live', hubUrl: 'https://hub.example', token: 't' }, () => api));
    expect(screen.getByText(/checks that you are an owner/)).toBeTruthy();
    expect(screen.getByTestId('approve-act-0001')).toBeEnabled();
    await fireEvent.press(screen.getByTestId('approve-act-0001'));
    expect(await screen.findByText(/This token is not an owner/)).toBeTruthy();
    expect(approve).toHaveBeenCalledWith('act-0001');
    expect(screen.getByTestId('approve-act-0001')).toBeDisabled();
  });
});
