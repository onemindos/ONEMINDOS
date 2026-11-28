// SPDX-License-Identifier: Apache-2.0
// What an owner is asked to install (issue #1097, D-027). A request to install a desktop app carries only its
// Flatpak id; a person or an agent chose it. Under the approval queue this shows what Flathub says that id is (name,
// summary), read from the hub, and who the id belongs to. The id is reverse DNS, so org.gimp.GIMP is gimp.org: that
// is the app's own claim, not a check by OneMind, and the card says so.
import { useMemo } from 'react';
import { OneMind } from '@onemind/sdk';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

/** The domain an application id claims: every part but the last, reversed (md.obsidian.Obsidian -> obsidian.md). */
export function publisherOf(appId: string): string {
  return appId.split('.').slice(0, -1).reverse().join('.');
}

type Found = { name: string; summary: string };

/** Render with key={appIds.join(',')} so a new request is looked up again. Not for demo mode (there is no Flathub). */
export function DesktopAppRequests({ appIds }: { appIds: string[] }) {
  const { token } = useSignedIn();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const details = usePoll(async () => {
    const out: Record<string, Found | undefined> = {};
    for (const id of appIds) {
      const r = await client.call<{ results?: Array<{ app_id?: string; name?: string; summary?: string }> }>({ method: 'GET', path: `/v1/desktop-apps/search?q=${encodeURIComponent(id)}` });
      const hit = (r.results ?? []).find((x) => x.app_id === id);
      out[id] = hit ? { name: hit.name ?? '', summary: hit.summary ?? '' } : undefined;
    }
    return out;
  }, 0);
  if (appIds.length === 0) return null;
  return (
    <section aria-label="Desktop apps waiting for approval" className="om-hint">
      <h2>Desktop apps waiting for approval</h2>
      {appIds.map((id) => {
        const d = details.data?.[id];
        return (
          <p key={id}>
            <strong>{d?.name || id}</strong> <code>{id}</code>
            {d?.summary ? <> · {d.summary}</> : null}
            {details.data && !d ? <> · Flathub did not list this id just now.</> : null}
            <br />
            Publisher it claims: {publisherOf(id)}. OneMind has not checked this claim. It runs in a sandbox with one folder of its own.
          </p>
        );
      })}
    </section>
  );
}
