// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useState } from 'react';
import { OneMind, type operations } from '@onemind/sdk';
import { deepLinkToPath } from '../lib/appLinks';
import { useSignedIn } from '../session';

type Hits = operations['search.query']['responses'][200]['content']['application/json'];
type TipMatch = { id: string; title: string; href: string };

export function useTipSearch(query: string): TipMatch[] {
  const { token, mock } = useSignedIn();
  const text = query.trim().slice(0, 200);
  const request = useMemo(() => ({ text, token, mock }), [text, token, mock]);
  const [result, setResult] = useState<{ request: typeof request; tips: TipMatch[] }>();

  useEffect(() => {
    const { text, token, mock } = request;
    if (!text || mock) return;
    let current = true;
    const timer = window.setTimeout(() => {
      const client = new OneMind({ baseUrl: window.location.origin, token, retries: 0 });
      const params = new URLSearchParams({ q: text, types: 'tip', limit: '6' });
      void client.call<Hits>({ method: 'GET', path: `/v1/search?${params}` }).then(hits => {
        if (!current) return;
        const tips = hits.flatMap(hit => {
          const href = deepLinkToPath(hit.link);
          return hit.app_id === 'tips' && hit.type === 'tip' && href === `/apps/tips/${hit.id}`
            ? [{ id: hit.id, title: hit.title, href: `/tips/${hit.id}` }] : [];
        });
        setResult({ request, tips });
      }, () => {
        if (current) setResult(undefined);
      });
    }, 200);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [request]);

  return result?.request === request ? result.tips : [];
}
