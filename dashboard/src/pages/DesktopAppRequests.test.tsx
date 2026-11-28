// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DesktopAppRequests, publisherOf } from './DesktopAppRequests';

vi.mock('../session', () => ({ useSignedIn: () => ({ token: 't' }) }));
vi.mock('../lib/hooks', async () => {
  const react = await import('react');
  return {
    usePoll: <T,>(fn: () => Promise<T>) => {
      const [data, setData] = react.useState<T>();
      react.useEffect(() => { void fn().then(setData); }, []);
      return { data };
    },
  };
});

afterEach(() => vi.unstubAllGlobals());

it('derives the publisher an application id claims', () => {
  expect(publisherOf('md.obsidian.Obsidian')).toBe('obsidian.md');
  expect(publisherOf('org.gimp.GIMP')).toBe('gimp.org');
});

it('shows what Flathub says an asked-for app is, and that the publisher is only claimed', async () => {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    paths.push(new URL(String(url)).pathname + new URL(String(url)).search);
    return new Response(JSON.stringify({ results: [{ app_id: 'md.obsidian.Obsidian', name: 'Obsidian', summary: 'Knowledge base on local Markdown' }] }), { status: 200, headers: { 'content-type': 'application/json' } });
  }));
  render(<DesktopAppRequests appIds={['md.obsidian.Obsidian']} />);
  expect(await screen.findByText('Obsidian')).toBeInTheDocument();
  expect(screen.getByText(/Knowledge base on local Markdown/)).toBeInTheDocument();
  expect(screen.getByText(/Publisher it claims: obsidian\.md\. OneMind has not checked this claim/)).toBeInTheDocument();
  expect(paths).toEqual(['/v1/desktop-apps/search?q=md.obsidian.Obsidian']);
});
