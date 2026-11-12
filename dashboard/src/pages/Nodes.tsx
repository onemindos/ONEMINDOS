import type { Board, NodeRecord } from '../api/types';
import { ErrorNote, Loading, StatusBadge } from '../components/bits';
import { useNow, usePoll } from '../lib/hooks';
import { effectiveStatus, formatAgo, hubNow, secondsSince, type Freshness } from '../lib/time';
import { useSignedIn } from '../session';

const BOARD_LABEL: Record<Board, string> = {
  'x86_64-efi': 'x86-64 PC (UEFI)',
  'arm64-efi': 'ARM64 (UEFI)',
  rpi5: 'Raspberry Pi 5',
  'jetson-orin': 'NVIDIA Jetson Orin',
  vm: 'Virtual machine',
  'vm-do': 'DigitalOcean droplet',
  unknown: 'Unknown board',
};

function gb(mb: number) {
  return `${(mb / 1024).toFixed(1)} GB`;
}

function NodeCard({ node, now, fresh }: { node: NodeRecord; now: number; fresh: Freshness }) {
  const status = effectiveStatus(node.status, node.last_seen, now, fresh);
  const live = status === 'online';
  const ago = formatAgo(secondsSince(node.last_seen, hubNow(now, fresh)));
  const titleId = `node-${node.node_id}`;
  return (
    <li>
      <article className={`node-card node-${status}`} aria-labelledby={titleId}>
        <header className="node-head">
          <div>
            <h2 id={titleId}>{node.hostname}</h2>
            <p className="small">
              {BOARD_LABEL[node.board] ?? node.board} · {node.role === 'hub' ? 'Hub' : 'Node'}
            </p>
          </div>
          <StatusBadge status={status} />
        </header>
        <p className="small last-seen">
          Last seen <strong>{ago}</strong>
          {!live && (
            <>
              {' — '}
              <span className="not-live">values below are the last report, not live</span>
            </>
          )}
        </p>
        <dl className={`facts ${live ? '' : 'facts-stale'}`}>
          <div>
            <dt>Board / arch</dt>
            <dd>
              {node.board} · {node.arch}
            </dd>
          </div>
          <div>
            <dt>OS</dt>
            <dd>{node.os.pretty}</dd>
          </div>
          <div>
            <dt>Kernel</dt>
            <dd>{node.kernel}</dd>
          </div>
          <div>
            <dt>k3s</dt>
            <dd>
              {node.k3s.present ? `${node.k3s.role ?? 'present'} · ${node.k3s.ready ? 'ready' : 'not ready'}` : 'not installed'}
            </dd>
          </div>
          <div>
            <dt>Boot slot</dt>
            <dd>{node.rauc.present ? (node.rauc.booted_slot ?? 'unknown') : 'no A/B (developer install)'}</dd>
          </div>
          <div>
            <dt>CPU</dt>
            <dd>
              {node.cpus} × {node.cpu_model}
            </dd>
          </div>
          <div>
            <dt>Memory free</dt>
            <dd>
              {gb(node.mem_available_mb)} of {gb(node.mem_total_mb)}
            </dd>
          </div>
          <div>
            <dt>Disk free</dt>
            <dd>
              {node.disk_free_gb.toFixed(1)} GB of {node.disk_total_gb.toFixed(1)} GB
            </dd>
          </div>
          {node.gpu.nvidia && (
            <div>
              <dt>GPU</dt>
              <dd>{node.gpu.model ?? 'NVIDIA'}</dd>
            </div>
          )}
          <div>
            <dt>Secure Boot / TPM</dt>
            <dd>
              {node.secure_boot} · {node.tpm2 ? 'TPM 2.0' : 'no TPM'}
            </dd>
          </div>
        </dl>
        <p className="fineprint">
          id <code>{node.node_id}</code> · agent {node.agent_version}
        </p>
      </article>
    </li>
  );
}

export function Nodes() {
  const { api } = useSignedIn();
  const now = useNow();
  const nodes = usePoll(() => api.nodes());
  const fresh: Freshness = { fetchedAt: nodes.fetchedAt, hubOffsetMs: api.hubOffsetMs() };
  return (
    <div className="page">
      <h1>Machines</h1>
      <p className="lede">
        Every machine that has joined this OneMind. A machine is <em>stale</em> after 30 s without a heartbeat and{' '}
        <em>offline</em> after 120 s.
      </p>
      {nodes.error && <ErrorNote error={nodes.error} fetchedAt={nodes.fetchedAt} now={now} />}
      {nodes.loading && !nodes.data ? (
        <Loading what="machines" />
      ) : nodes.data && nodes.data.length === 0 ? (
        <p>No machines have reported yet.</p>
      ) : (
        <ul className="card-grid">
          {(nodes.data ?? []).map((n) => (
            <NodeCard key={n.node_id} node={n} now={now} fresh={fresh} />
          ))}
        </ul>
      )}
    </div>
  );
}
