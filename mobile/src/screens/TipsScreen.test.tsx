// SPDX-License-Identifier: Apache-2.0
import type { components } from '@onemind/sdk';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { Linking } from 'react-native';
import { AppRoot } from '../../App';
import { Features, HttpApi, OP, type FetchLike } from '../api/client';
import { v0Api } from '../test/fakes';

jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

jest.mock('expo-file-system', () => {
  const files = new Map<string, string>();
  class Directory {
    readonly uri: string;
    constructor(parent: string, name: string) { this.uri = parent + '/' + name; }
    create() {}
  }
  class File {
    uri: string;
    constructor(parent: Directory, name: string) { this.uri = parent.uri + '/' + name; }
    get exists() { return files.has(this.uri); }
    async text() { return files.get(this.uri); }
    async write(contents: string) { files.set(this.uri, contents); }
    async move(target: File) {
      const content = files.get(this.uri);
      if (content === undefined) throw new Error('Missing file');
      files.set(target.uri, content);
      this.delete();
      this.uri = target.uri;
    }
    delete() { files.delete(this.uri); }
  }
  return { Directory, File, Paths: { cache: 'file:///cache' } };
});

const hubUrl = 'https://hub.example';
const tip: components['schemas']['TipView'] = {
  id: 'read-approvals', title: 'Read approvals', body: 'Read an approval before deciding.',
  collection: 'getting-started', opens: { dashboard: '/approvals', phone: 'onemind://approvals' },
  clip: null, skip_if_done: [], state: 'new', state_updated_at: null,
};

const pack: components['schemas']['TipList'] = { pack: { version: '0.1.0', source: 'image' }, tips: [tip] };

function mount(fetchFn: FetchLike, token = 'owner-fixture-token') {
  return render(<AppRoot deps={{
    load: async () => ({ mode: 'live', hubUrl, token }),
    makeApi: (connection, tokens) => Object.assign(
      new HttpApi({ baseUrl: connection.hubUrl, tokens, fetchFn }),
      v0Api({ features: async () => new Features([OP.tips], 'openapi') }),
    ),
  }} />);
}

afterEach(() => jest.restoreAllMocks());

it('opens Tips from Me, then opens a saved tip from a cold deep link offline', async () => {
  const initialUrl = jest.spyOn(Linking, 'getInitialURL').mockResolvedValue(null);
  const fetchHub = jest.fn<ReturnType<FetchLike>, Parameters<FetchLike>>(async () => (
    new Response(JSON.stringify(pack), { status: 200, headers: { 'content-type': 'application/json' } })
  ));
  const active = await mount(fetchHub);
  await fireEvent.press(await screen.findByTestId('tab-me'));
  await fireEvent.press(await screen.findByTestId('more-Tips'));
  expect(await screen.findByRole('button', { name: tip.title })).toBeTruthy();
  expect(fetchHub).toHaveBeenCalledWith(hubUrl + '/v1/tips', expect.objectContaining({ method: 'GET' }));
  await active.unmount();

  initialUrl.mockResolvedValue('onemind://tips/' + tip.id);
  fetchHub.mockRejectedValue(new TypeError('Offline'));
  const offline = await mount(fetchHub);
  expect(await screen.findByRole('header', { name: tip.title })).toBeTruthy();
  expect(screen.getByText(tip.body)).toBeTruthy();
  expect(screen.getByText('Offline · saved on this phone')).toBeTruthy();
  await offline.unmount();

  initialUrl.mockResolvedValue('onemind://tips');
  await mount(fetchHub, 'another-fixture-token');
  expect(await screen.findByText(/No Tips pack is saved for this connection/)).toBeTruthy();
  expect(screen.queryByText(tip.body)).toBeNull();
});
