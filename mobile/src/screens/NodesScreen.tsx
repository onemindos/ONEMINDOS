// SPDX-License-Identifier: Apache-2.0
import { Text, View } from 'react-native';
import type { NodeRecord } from '../api/types';
import { useHubData, useNow } from '../data';
import { effectiveStatus, formatAgo, secondsSince, type Freshness } from '../lib/time';
import { Badge, Card, H1, Loading, Notice, P, Row, Screen, STATUS_TONE, s } from '../ui/bits';
import { useTheme } from '../ui/theme';

const gb = (mb: number) => `${(mb / 1024).toFixed(1)} GB`;

function NodeCard({ n, now, f }: { n: NodeRecord; now: number; f: Freshness }) {
  const t = useTheme();
  const status = effectiveStatus(n.status, n.last_seen, now, f);
  const ago = formatAgo(secondsSince(n.last_seen, now + (f.hubOffsetMs ?? 0)));
  return (
    <Card testID={`node-${n.node_id}`}>
      <View style={s.row}>
        <Text style={{ color: t.text, fontSize: 17, fontWeight: '600' }}>{n.hostname}</Text>
        <Badge label={status} tone={STATUS_TONE[status]} />
      </View>
      <P muted small>
        {n.role} · {n.node_id} · last seen {ago}
      </P>
      {status !== 'online' && (
        <Notice
          tone={status === 'offline' ? 'bad' : 'warn'}
          text={`Not live. The values below are from the last heartbeat, ${ago}.`}
        />
      )}
      <Row label="Board" value={`${n.board} · ${n.arch}`} />
      <Row label="OS" value={n.os.pretty} />
      <Row label="CPU" value={`${n.cpu_model} · ${n.cpus} CPU${n.cpus === 1 ? "" : "s"}`} />
      <Row label="Memory free" value={`${gb(n.mem_available_mb)} of ${gb(n.mem_total_mb)}`} />
      <Row label="Disk free" value={`${n.disk_free_gb.toFixed(0)} of ${n.disk_total_gb.toFixed(0)} GB`} />
      <Row label="k3s" value={n.k3s.present ? `${n.k3s.role ?? 'unknown'} · ${n.k3s.ready ? 'ready' : 'not ready'}` : 'not installed'} />
      <Row label="OS slot" value={n.rauc.present ? `booted ${n.rauc.booted_slot ?? 'unknown'}` : 'no A/B (developer install)'} />
      {n.gpu.nvidia && <Row label="GPU" value={n.gpu.model ?? 'NVIDIA'} />}
      <Row label="Security" value={`TPM ${n.tpm2 ? 'yes' : 'no'} · Secure Boot ${n.secure_boot}`} />
      {n.update && (
        <Row
          label="OS update"
          value={`${n.update.state}${n.update.available_version ? ` → ${n.update.available_version}` : ''} (${n.update.channel})`}
        />
      )}
      <Row label="Agent" value={n.agent_version} />
    </Card>
  );
}

export function NodesScreen() {
  const now = useNow();
  const { nodes, fetchedAt, hubOffsetMs, loading } = useHubData();
  if (loading && !nodes) return <Loading what="nodes" />;
  const list = [...(nodes ?? [])].sort((a, b) => (a.role === 'hub' ? -1 : b.role === 'hub' ? 1 : a.hostname.localeCompare(b.hostname)));
  return (
    <Screen testID="nodes">
      <H1>Nodes</H1>
      <P muted small>A node is stale after 30 s without a heartbeat and offline after 2 minutes.</P>
      {list.length === 0 ? <P muted>No node has reported yet.</P> : list.map((n) => <NodeCard key={n.node_id} n={n} now={now} f={{ fetchedAt, hubOffsetMs }} />)}
    </Screen>
  );
}
