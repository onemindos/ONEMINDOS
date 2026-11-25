// SPDX-License-Identifier: Apache-2.0
// Issue 697: the dashboard declares its protocol generation, and a hub that no longer serves it
// turns the whole app into "Update needed" instead of screens that misread its answers.
import { render, renderHook, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PROTOCOL_HEADER, PROTOCOL_MAX_HEADER, PROTOCOL_MIN_HEADER, PROTOCOL_VERSION } from '@onemind/sdk';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { SessionProvider } from '../session';
import { resetProtocolState, useUpdateNeeded } from './protocol';

const range = (min: number, max = min) => ({ [PROTOCOL_MIN_HEADER]: String(min), [PROTOCOL_MAX_HEADER]: String(max) });

afterEach(() => resetProtocolState());

describe('protocol generation (sdk/contracts/protocol-versions.md)', () => {
  it('sends X-OneMind-Protocol on every call, ours and the SDK’s', async () => {
    const f = vi.fn(async () => Response.json({ name: 'box', version: '0', hub_node_id: null }, { headers: range(1, PROTOCOL_VERSION) }));
    const api = new HttpApi({ token: 't', fetchFn: f });
    await api.onboardingState().catch(() => undefined);
    await api.instance();
    for (const [, init] of f.mock.calls as unknown as [string, RequestInit][]) {
      expect((init.headers as Record<string, string>)[PROTOCOL_HEADER]).toBe(String(PROTOCOL_VERSION));
    }
    expect(f.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('a hub that still serves this build, or predates the headers, changes nothing', async () => {
    const api = new HttpApi({ token: 'owner', fetchFn: vi.fn(async () => Response.json({ name: 'box', version: '0', hub_node_id: null }, { headers: range(1, PROTOCOL_VERSION) })) });
    await api.instance();
    const old = new HttpApi({ token: 'owner', fetchFn: vi.fn(async () => Response.json({ name: 'box', version: '0', hub_node_id: null })) });
    await old.instance();
    const { result } = renderHook(() => useUpdateNeeded());
    expect(result.current).toBeNull();
  });

  // Last: the App it renders keeps polling the refusing hub until the test environment ends.
  it('shows Update needed when the hub has moved past this build', async () => {
    const refusal = () => Response.json(
      { error: 'upgrade_required', reason: 'protocol_too_old', message: 'Update the app.' },
      { status: 400, headers: range(PROTOCOL_VERSION + 1) },
    );
    const api = new HttpApi({ token: 'owner', fetchFn: vi.fn(async () => refusal()) });
    window.sessionStorage.setItem('onemind.token', 'owner');
    render(<MemoryRouter><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'o', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Update needed' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(`speaks OneMind protocol ${PROTOCOL_VERSION}. The hub now serves ${PROTOCOL_VERSION + 1} to ${PROTOCOL_VERSION + 1}`);
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });
});
