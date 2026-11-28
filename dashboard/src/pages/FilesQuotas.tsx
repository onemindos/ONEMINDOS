// SPDX-License-Identifier: Apache-2.0
// Files > Storage limits (owner only): how much each person's files may use, and how much they use now.
// GET /v1/files/quotas and PUT /v1/files/quotas/{person_id}. The shared space is read only here: its limit is a
// box setting. The CLI twin is `onemind files quotas list|set` in #1247 (the CLI data groups change).
import { useState } from 'react';
import { Button, Card } from '@onemind/ui';
import { human, type FilesApi, type Quota } from '../files/api';
import { usePoll } from '../lib/hooks';
import { Load, type useRun } from './parts';

// Decimal gigabytes, the same unit human() shows and `onemind files quotas set --gb` writes (gb * 1e9):
// typing 5 saves 5,000,000,000 bytes and the row reads "of 5.0 GB".
const GB = 1e9;

export function FilesQuotas({ api, run }: { api: FilesApi; run: ReturnType<typeof useRun> }) {
  const quotas = usePoll(() => api.quotas(), 60_000);
  return (
    <Card title="Storage limits" as="section">
      <p>Each person’s files, their trash and uploads in progress count towards their limit. Leave a limit empty for no limit.</p>
      <Load res={quotas} what="Reading storage limits">
        {(rows) => rows.length === 0 ? (
          <p className="om-hint">No person has a home space yet. Limits appear here once someone signs in and stores a file.</p>
        ) : (
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
  const [gb, setGb] = useState(q.limit_bytes === null ? '' : String(Math.round((q.limit_bytes / GB) * 100) / 100));
  const name = q.person_id ?? 'Shared space';
  // A limit of 0 would block every write and upload for this person, so it is refused here, as the CLI
  // refuses --gb 0. "No limit" is an empty field, not 0.
  const empty = gb.trim() === '';
  const valid = empty || (Number.isFinite(Number(gb)) && Number(gb) > 0);
  const hintId = `quota-${q.root}-hint`;
  return (
    <li>
      <strong>{name}</strong> uses {human(q.used_bytes)}
      {q.limit_bytes === null ? ', no limit' : ` of ${human(q.limit_bytes)}`}
      {q.person_id ? (
        <form
          aria-label={`Limit for ${name}`}
          onSubmit={(e) => {
            e.preventDefault();
            if (valid) void onSave(empty ? null : Math.round(Number(gb) * GB));
          }}
        >
          <label htmlFor={`quota-${q.root}`}>Limit for {name} in GB (empty for none)</label>
          <input id={`quota-${q.root}`} inputMode="decimal" value={gb} onChange={(e) => setGb(e.target.value)} aria-invalid={!valid} aria-describedby={valid ? undefined : hintId} />
          {!valid && <span id={hintId} className="om-hint" role="alert">Type a number of GB above 0, or leave it empty for no limit. A limit of 0 would stop {name} saving anything.</span>}
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
