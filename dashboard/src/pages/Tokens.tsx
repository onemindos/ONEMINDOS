// SPDX-License-Identifier: Apache-2.0
// Settings > API tokens and agents: GET/POST /v1/tokens, POST …/rotate, DELETE (revoke). A new token
// is shown once in a dialog and kept only in component state. An agent token is minted with the
// gateway's reader scopes (F-15): it can read and ask, and anything it asks waits in Approvals.
import { useState, type FormEvent } from 'react';
import { Button, Card, Dialog, PageHeader, StatusPill, Table } from '@onemind/ui';
import type { TokenInfo } from '../api/wiring';
import { useHub } from '../data/hub';
import { t } from '../i18n';
import { usePoll } from '../lib/hooks';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Load, OneTimeDialog, TextField, useRun } from './parts';

const AGENT_ID = /^[a-z0-9][a-z0-9._-]{0,62}$/;

export function Tokens() {
  const { api } = useSignedIn();
  const hub = useHub();
  const run = useRun();
  const tokens = usePoll(() => api.tokens(), 0);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [agent, setAgent] = useState(false);
  const [agentId, setAgentId] = useState('');
  const [secret, setSecret] = useState<string>();
  const bad = agent && !AGENT_ID.test(agentId);

  const create = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || bad) return;
    void run(async () => {
      const made = await api.createToken({ name: name.trim(), ...(agent ? { principal: { kind: 'agent' as const, id: `agent:${agentId}` } } : {}) });
      setOpen(false);
      setName('');
      setAgentId('');
      setSecret(made.one_time.token);
      await tokens.reload();
    }, t('tokens.create'));
  };
  const rotate = (tok: TokenInfo) =>
    void run(async () => {
      const made = await api.rotateToken(tok.id);
      setSecret(made.one_time.token);
      await tokens.reload();
    }, t('tokens.rotate', { name: tok.name }));

  return (
    <div className="dash-stack">
      <PageHeader title={t('tokens.title')} lede={t('tokens.lede')} />
      <Card title={t('tokens.title')} aside={<Button size="sm" icon="plus" onClick={() => setOpen(true)}>{t('tokens.create')}</Button>}>
        <Load res={tokens} what="Loading tokens">
          {(rows) => (
            <Table
              caption={t('tokens.title')}
              hideCaption
              rows={rows}
              rowKey={(r) => r.id}
              columns={[
                { key: 'name', header: t('tokens.name'), render: (r) => r.name },
                { key: 'kind', header: 'Kind', render: (r) => (r.kind === 'agent' ? <StatusPill tone="agent" label="AI agent" /> : <StatusPill tone="neutral" label="Person" />) },
                { key: 'who', header: 'Acts as', render: (r) => r.principal_id, secondary: true },
                { key: 'used', header: 'Last used', render: (r) => (r.last_used_at ? formatAgo(secondsSince(r.last_used_at, hub.now)) : t('common.never')), secondary: true },
                {
                  key: 'x',
                  header: 'Actions',
                  render: (r) =>
                    r.revoked_at || r.source === 'file' ? (
                      <span className="om-hint">{r.revoked_at ? 'Revoked' : 'Install token'}</span>
                    ) : (
                      <span className="dash-actions">
                        <Button size="sm" variant="ghost" aria-label={t('tokens.rotate', { name: r.name })} onClick={() => rotate(r)}>Rotate</Button>
                        <Button size="sm" variant="danger" aria-label={t('tokens.revoke', { name: r.name })} onClick={() => void run(async () => { await api.revokeToken(r.id); await tokens.reload(); }, t('tokens.revoke', { name: r.name }))}>Revoke</Button>
                      </span>
                    ),
                },
              ]}
            />
          )}
        </Load>
      </Card>
      <Dialog open={open} onClose={() => setOpen(false)} title={t('tokens.create')} actions={<><Button variant="ghost" onClick={() => setOpen(false)}>{t('common.cancel')}</Button><Button variant="primary" onClick={create} disabled={bad}>{t('tokens.create')}</Button></>}>
        <form className="dash-form" onSubmit={create}>
          <TextField id="token-name" label={t('tokens.name')} value={name} onChange={setName} />
          <label><input type="checkbox" checked={agent} onChange={(e) => setAgent(e.target.checked)} /> {t('tokens.agent')}</label>
          {agent && <TextField id="agent-id" label={t('tokens.agentId')} value={agentId} onChange={setAgentId} />}
          {bad && <p className="om-hint">Use lower-case letters, digits, dots, dashes or underscores.</p>}
        </form>
      </Dialog>
      <OneTimeDialog title={t('tokens.create')} note={t('tokens.shown')} secret={secret} onClose={() => setSecret(undefined)} />
    </div>
  );
}
