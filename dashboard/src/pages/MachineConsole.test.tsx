// SPDX-License-Identifier: Apache-2.0
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MachineConsole } from './MachineConsole';

class TestSocket extends EventTarget {
  close = vi.fn();
  constructor(readonly url: URL, readonly protocol: string) { super(); sockets.push(this); }
}
const sockets: TestSocket[] = [];
const clients: TestDisplay[] = [];
class TestDisplay extends EventTarget {
  disconnect = vi.fn();
  viewOnly = false;
  constructor(_target: HTMLElement, readonly socket: TestSocket) { super(); clients.push(this); }
}
vi.mock('@novnc/novnc', () => ({ get default() { return TestDisplay; } }));

function ticket(value: string, path = '/v1/machines/web/console/ws') {
  return Response.json({ machine: 'web', path, ticket: value, broker: 'ready' });
}

function openWindow() {
  return render(<StrictMode><MemoryRouter><MachineConsole name="web" token="owner-demo" /></MemoryRouter></StrictMode>);
}
beforeEach(() => { sockets.length = 0; clients.length = 0; vi.stubGlobal('WebSocket', TestSocket); });
afterEach(() => vi.unstubAllGlobals());

it('opens one broker connection, gets a new view-only ticket and reports takeover', async () => {
  let count = 0;
  const post = vi.fn<typeof fetch>(async () => ticket('once-' + ++count));
  vi.stubGlobal('fetch', post);
  const page = openWindow();
  await waitFor(() => expect(clients).toHaveLength(1));
  const [path, init] = post.mock.calls[0]!;
  expect(path).toBe(window.location.origin + '/v1/machines/web/console');
  expect(init?.method).toBe('POST');
  expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer owner-demo');
  expect(post).toHaveBeenCalledTimes(1);
  const first = sockets[0]!;
  expect(first.url.toString()).toBe(window.location.origin.replace(/^http/, 'ws') + '/v1/machines/web/console/ws?ticket=once-1');
  expect(first.protocol).toBe('binary');
  expect(clients[0]!.socket).toBe(first);
  act(() => { clients[0]!.dispatchEvent(new Event('connect')); });
  expect(screen.getByRole('status')).toHaveTextContent('Connected');
  fireEvent.click(screen.getByRole('checkbox', { name: 'View only' }));
  await waitFor(() => expect(clients).toHaveLength(2));
  expect(clients[0]!.disconnect).toHaveBeenCalled();
  expect(sockets[1]!.url.searchParams.get('ticket')).toBe('once-2');
  expect(sockets[1]!.url.searchParams.get('view')).toBe('1');
  expect(clients[1]!.viewOnly).toBe(true);
  act(() => {
    sockets[1]!.dispatchEvent(new CloseEvent('close', { code: 4001 }));
    clients[1]!.dispatchEvent(new Event('disconnect'));
  });
  expect(screen.getByRole('status')).toHaveTextContent('Another console took over');
  expect(document.body.textContent).not.toContain('once-');
  page.unmount();
  expect(clients[1]!.disconnect).toHaveBeenCalled();
});

it('dismisses a late ticket after the window closes', async () => {
  let resolve!: (r: Response) => void;
  const post = vi.fn(() => new Promise<Response>((done) => { resolve = done; }));
  vi.stubGlobal('fetch', post);
  const page = openWindow();
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  page.unmount();
  await act(async () => resolve(ticket('unused')));
  expect(sockets).toHaveLength(0);
});

it('requests fullscreen for the window containing the viewer and its controls', async () => {
  Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, value: true });
  try {
    vi.stubGlobal('fetch', async () => ticket('single-use'));
    openWindow();
    await waitFor(() => expect(clients).toHaveLength(1));
    const frame = screen.getByRole('region', { name: 'web display' }).closest('section')!;
    frame.requestFullscreen = vi.fn().mockResolvedValue(undefined);
    fireEvent.click(screen.getByRole('button', { name: 'Fullscreen' }));
    expect(frame.requestFullscreen).toHaveBeenCalledOnce();
  } finally {
    Reflect.deleteProperty(document, 'fullscreenEnabled');
  }
});

it.each([
  ['foreign endpoint', () => ticket('private', 'wss://foreign.example/ws')],
  ['stopped machine', () => Response.json({ error: 'conflict' }, { status: 409 })],
  ['agent refused', () => Response.json({ error: 'permission_denied' }, { status: 403 })],
])('never opens a socket after %s', async (_name, answer) => {
  vi.stubGlobal('fetch', async () => answer());
  openWindow();
  await screen.findByRole('alert');
  expect(sockets).toHaveLength(0);
  expect(document.body.textContent).not.toContain('private');
});
