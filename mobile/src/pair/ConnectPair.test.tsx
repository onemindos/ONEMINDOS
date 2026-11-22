// SPDX-License-Identifier: Apache-2.0
// Issue 716 on the Connect screen: scan or type the join QR, the box CA is checked and pinned, the same short
// code is shown, and the enrolment code finishes the join. The box is a test double of /v1/tls/ca.crt and
// /v1/auth/enrol; the camera is a stand-in that hands over one scanned text.
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { ConnectScreen } from '../screens/ConnectScreen';
import { SessionProvider } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { loadPin, wasUsed } from './pair';
import { caSha256 } from './trust';

const camera: { onBarcodeScanned?: (r: { data: string }) => void } = {};
jest.mock('expo-camera', () => ({
  useCameraPermissions: () => [{ granted: true, canAskAgain: true }, jest.fn()],
  CameraView: (p: { onBarcodeScanned?: (r: { data: string }) => void }) => {
    camera.onBarcodeScanned = p.onBarcodeScanned;
    return null;
  },
}));

const BOX_CA = new TextEncoder().encode('box CA certificate (DER stand-in) for the screen test');
const HUB = 'https://box1.local:8443';
const qr = (o: { hub?: string; ca?: string; code: string }) =>
  `onemind-join:v2?hub=${encodeURIComponent(o.hub ?? HUB)}&ca=${o.ca ?? caSha256(BOX_CA)}&code=${o.code}&kind=phone`;

let served = BOX_CA;
const calls: string[] = [];
const realFetch = globalThis.fetch;
beforeEach(() => {
  served = BOX_CA;
  calls.length = 0;
  globalThis.fetch = jest.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push(`${init?.method ?? 'GET'} ${url}`);
    if (url === `${HUB}/v1/tls/ca.crt`) return new Response(served, { status: 200 });
    if (url === `${HUB}/v1/auth/enrol` && JSON.parse(String(init?.body)).code === 'enrol-ok')
      return new Response(JSON.stringify({ access_token: 'at', expires_at: '2030-01-01T00:00:00Z', refresh_token: 'rt' }), { status: 201 });
    if (url === `${HUB}/v1/auth/enrol`) return new Response(JSON.stringify({ error: 'unauthenticated', message: 'unknown or expired enrolment code', reason: 'code_unknown' }), { status: 401 });
    throw new TypeError('Network request failed');
  }) as typeof fetch;
});
afterAll(() => {
  globalThis.fetch = realFetch;
});

async function renderConnect() {
  const save = jest.fn(async (_c: Connection) => undefined);
  await render(
    <SessionProvider deps={{ load: async () => null, save, clear: async () => undefined, makeApi: () => v0Api() }}>
      <ConnectScreen />
    </SessionProvider>,
  );
  return save;
}

describe('Connect: pair from the join QR (issue 716)', () => {
  it('scans the code, pins the box CA, shows the same short code, and joins with the enrolment code', async () => {
    const save = await renderConnect();
    await fireEvent.press(screen.getByTestId('scan-join'));
    await act(async () => camera.onBarcodeScanned?.({ data: qr({ code: 'SCAN-0001-AAAA' }) }));
    expect(await screen.findByTestId('join-short-code')).toHaveTextContent('SCAN-0001-AAAA');
    expect(await loadPin()).toMatchObject({ ca: caSha256(BOX_CA), hubUrl: HUB, mode: 'system' });
    // No native module in tests, so system mode: the screen must not claim a pin it did not make.
    expect(screen.queryByText(/is pinned here/)).toBeNull();
    expect(screen.getByText(/only the phone's own trust store/)).toBeTruthy();
    expect(screen.getByTestId('hub-url').props.value).toBe(HUB);

    await fireEvent.changeText(screen.getByTestId('enrol-code'), 'enrol-ok');
    await fireEvent.changeText(screen.getByTestId('enrol-password'), 'correct horse battery');
    await fireEvent.press(screen.getByTestId('enrol'));
    await act(async () => undefined);
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ mode: 'live', hubUrl: HUB, token: 'at', refreshToken: 'rt' }));
    expect(calls).toEqual([`GET ${HUB}/v1/tls/ca.crt`, `POST ${HUB}/v1/auth/enrol`]);
    // The join QR is now spent on this phone.
    expect(await wasUsed('SCAN-0001-AAAA')).toBe(true);
  });

  it('refuses a typed code that points at plain http, and sends nothing', async () => {
    const save = await renderConnect();
    await fireEvent.changeText(screen.getByTestId('join-code'), qr({ hub: 'http://box1.local:8080', code: 'TYPE-0002-HTTP' }));
    await fireEvent.press(screen.getByTestId('use-join-code'));
    expect(await screen.findByText(/plain http:\/\/ address/)).toBeTruthy();
    expect(screen.queryByTestId('join-short-code')).toBeNull();
    expect(calls).toEqual([]);
    expect(save).not.toHaveBeenCalled();
  });

  it('refuses a box serving a different certificate than the code: nothing pinned, no sign-in offered', async () => {
    served = new TextEncoder().encode('somebody else in between');
    const before = await loadPin();
    await renderConnect();
    await fireEvent.changeText(screen.getByTestId('join-code'), qr({ code: 'TYPE-0003-M1TM' }));
    await fireEvent.press(screen.getByTestId('use-join-code'));
    expect(await screen.findByText(/different box certificate/)).toBeTruthy();
    expect(screen.queryByTestId('join-short-code')).toBeNull();
    expect(screen.queryByTestId('enrol')).toBeNull();
    expect(await loadPin()).toEqual(before);
  });
});
