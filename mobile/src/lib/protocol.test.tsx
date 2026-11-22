// SPDX-License-Identifier: Apache-2.0
// Issue 697: the phone app declares its protocol generation, and a hub that no longer serves it
// turns the whole app into "Update needed" instead of a crash or screens that misread its answers.
import { render, screen } from '@testing-library/react-native';
import App from '../../App';
import { HttpApi } from '../api/client';
import { BUILT_IN_PROTOCOL, PROTOCOL_HEADER, PROTOCOL_MAX_HEADER, PROTOCOL_MIN_HEADER, PROTOCOL_VERSION, protocolVersion, resetProtocolState } from './protocol';

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

const range = (min: number, max = min) => ({ [PROTOCOL_MIN_HEADER]: String(min), [PROTOCOL_MAX_HEADER]: String(max) });
const instance = { name: 'box', version: '0', hub_node_id: null };

afterEach(() => resetProtocolState());

describe('protocol generation (sdk/contracts/protocol-versions.md)', () => {
  it('speaks a generation the committed OpenAPI contract serves (N or N-1)', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const spec = require('../../../sdk/openapi/onemind-v1.json') as { info: { 'x-onemind-protocol': { header: string; current: number } } };
    const proto = spec.info['x-onemind-protocol'];
    expect(proto.header).toBe(PROTOCOL_HEADER);
    expect(BUILT_IN_PROTOCOL).toBeLessThanOrEqual(proto.current);
    expect(BUILT_IN_PROTOCOL).toBeGreaterThanOrEqual(proto.current - 1);
  });

  it('a lab build may only lower its generation', () => {
    expect(protocolVersion(undefined)).toBe(BUILT_IN_PROTOCOL);
    expect(protocolVersion('1')).toBe(1);
    for (const bad of ['0', String(BUILT_IN_PROTOCOL + 1), 'two', '1.5', '']) expect(protocolVersion(bad)).toBe(BUILT_IN_PROTOCOL);
  });

  it('sends X-OneMind-Protocol and keeps working with a hub that serves it', async () => {
    const calls: RequestInit[] = [];
    const api = new HttpApi({ baseUrl: 'https://hub.test', token: 't', fetchFn: async (_u, init) => (calls.push(init ?? {}), Response.json(instance, { headers: range(1, PROTOCOL_VERSION) })) });
    expect((await api.instance()).name).toBe('box');
    expect((calls[0]!.headers as Record<string, string>)[PROTOCOL_HEADER]).toBe(String(PROTOCOL_VERSION));
  });

  it('shows Update needed when the hub has moved past this build', async () => {
    const refusal = () => Response.json({ error: 'upgrade_required', reason: 'protocol_too_old', message: 'Update the app.' }, { status: 400, headers: range(PROTOCOL_VERSION + 1) });
    const api = new HttpApi({ baseUrl: 'https://hub.test', token: 't', fetchFn: async () => refusal() });
    await expect(api.instance()).rejects.toMatchObject({ code: 'upgrade_required' });
    await render(<App />);
    expect(await screen.findByTestId('update-needed')).toBeTruthy();
    expect(screen.getByText('Update needed')).toBeTruthy();
    expect(screen.getByText(new RegExp(`speaks protocol ${PROTOCOL_VERSION}\\. Your hub now serves ${PROTOCOL_VERSION + 1} to ${PROTOCOL_VERSION + 1}`))).toBeTruthy();
  });
});
