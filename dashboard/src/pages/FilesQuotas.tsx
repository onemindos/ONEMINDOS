// SPDX-License-Identifier: Apache-2.0
// Files > Storage limits (owner only): how much each person's files may use, and how much they use now.
// GET /v1/files/quotas and PUT /v1/files/quotas/{person_id}. The shared space is read only here: its limit is a
// box setting. The CLI twin is `onemind files quotas list|set` (the CLI data groups change).
import { useState } from 'react';
import { Button, Card } from '@onemind/ui';
import { human, type FilesApi, type Quota } from '../files/api';
import { usePoll } from '../lib/hooks';
import { Load, type useRun } from './parts';

const GIB = 1024 ** 3;

export function FilesQuotas({ api, run }: { api: FilesApi; run: ReturnType<typeof useRun> }) {
  const quotas = usePoll(() => api.quotas(), 60_000);
  return (
    <Card title="Storage limits" as="section">
      <p>Each person’s files, their trash and uploads in progress count towards their limit. Leave a limit empty for no limit.</p>
      <Load res={quotas} what="Reading storage limits">
        {(rows) => (
          <ul aria-label="Storage per person">
            {rows.map((q) => (
              <QuotaRow key={q.root} q={q} onSave={async (bytes) => { if (q.person_id && (await run(() => api.setQuota(q.person_id!, bytes), 'Could not save the limit'))) await quotas.reload(); }} />
            ))}
          </ul>
        )}
      </Load>
    </Card>
  );
}

function QuotaRow({ q, onSave }: { q: Quota; onSave: (bytes: number | null) => Promise<void> }) {
  const [gb, setGb] = useState(q.limit_bytes === null ? '' : String(Math.round((q.limit_bytes / GIB) * 100) / 100));
  const name = q.person_id ?? 'Shared space';
  const valid = gb.trim() === '' || (Number.isFinite(Number(gb)) && Number(gb) >= 0);
  return (
    <li>
      <strong>{name}</strong> uses {human(q.used_bytes)}
      {q.limit_bytes === null ? ', no limit' : ` of ${human(q.limit_bytes)}`}
      {q.person_id ? (
        <form
          aria-label={`Limit for ${name}`}
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) void onSave(gb.trim() === '' ? null : Math.round(Number(gb) * GIB));
          }}
        >
          <label htmlFor={`quota-${q.root}`}>Limit for {name} in GB (empty for none)</label>
          <input id={`quota-${q.root}`} inputMode="decimal" value={gb} onChange={(e) => setGb(e.target.value)} aria-invalid={!valid} />
          <Button type="submit" size="sm" disabled={!valid}>
            Save limit
          </Button>
        </form>
      ) : (
        <span className="om-hint"> (set on the box, not here)</span>
      )}
    </li>
  );
}
