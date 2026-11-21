// SPDX-License-Identifier: Apache-2.0
// System screens under More (docs/design/IA.md §3 "System"): OS updates, System controls, Device info, Live
// usage and Network. Each is hidden from More when the hub does not serve its route. The phone reads, and
// files requests; an owner decides them in Approvals. Nothing here installs, restarts or shuts anything down.
import { useState } from 'react';
import { Text, View } from 'react-native';
import { OP } from '../api/client';
import type { Action, AppMetrics, SystemControlType, SystemPlanPreview } from '../api/types';
import { useHubData } from '../data';
import { formatBytes, requestError } from '../lib/manage';
import { CONTROL_LABEL, hubNode, installOffer, latestSample, pct, requestOsInstall, requestSystemControl, uptimeText, usedPct } from '../lib/system';
import { useLoad } from '../lib/useLoad';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Row, Screen, s, STATUS_TONE } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

const gb = (mb: number) => `${(mb / 1024).toFixed(1)} GB`;
const word = (v: string | null | undefined, none = 'not reported') => (v ? v : none);

function Unavailable({ testID, title }: { testID: string; title: string }) {
  return (
    <Screen testID={testID}>
      <H1>{title}</H1>
      <Notice text="This hub does not serve this yet, so there is nothing to show. It appears once the hub is updated." />
    </Screen>
  );
}

function Failed({ e, forbidden, what }: { e: { message: string }; forbidden: boolean; what: string }) {
  return <Notice tone={forbidden ? 'warn' : 'bad'} text={forbidden ? `This sign-in may not read ${what}.` : `Could not read ${what}: ${e.message}`} />;
}

// ---- OS updates ----

export function OsUpdatesScreen() {
  const { api, features, canRequest } = useSignedIn();
  const { actions, reload: reloadHub } = useHubData();
  const served = features.has(OP.osUpdates);
  const status = useLoad(() => (served ? api.osUpdates() : Promise.resolve(undefined)), [api, served]);
  const history = useLoad(() => (served && features.has(OP.osUpdateHistory) ? api.osUpdateHistory() : Promise.resolve(undefined)), [api, served, features]);
  const [busy, setBusy] = useState(false);
  const [filed, setFiled] = useState<Action>();
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  if (!served) return <Unavailable testID="os-updates" title="OS updates" />;
  if (status.loading) return <Loading what="OS updates" />;
  const live = filed ? ((actions ?? []).find((a) => a.id === filed.id) ?? filed) : undefined;

  async function ask(node: string, version: string) {
    setBusy(true);
    setMsg(undefined);
    try {
      setFiled(await requestOsInstall(api, node, version));
      setMsg({ text: 'Request sent. Nothing has been installed: it waits in Approvals until an owner decides.', tone: 'ok' });
      await Promise.all([reloadHub(), history.reload()]);
    } catch (e) {
      setMsg({ text: requestError(e, 'an OS update').text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  const d = status.data;
  return (
    <Screen testID="os-updates">
      <H1>OS updates</H1>
      {status.error && !d ? <Failed e={status.error} forbidden={status.forbidden} what="OS updates" /> : null}
      {d && d.install.available !== true ? <Notice tone="warn" text={`Installing from the hub is not available yet. ${d.install.message ?? ''}`.trim()} /> : null}
      {msg ? <Notice tone={msg.tone} text={msg.text} /> : null}
      {live ? <P small muted>Your request: {live.state.replace(/_/g, ' ')}</P> : null}
      {d && d.nodes.length === 0 ? <P muted>No machine has reported yet.</P> : null}
      {d?.nodes.map((n) => {
        const offer = installOffer(n);
        return (
          <Card key={n.node_id} testID={`os-node-${n.node_id}`}>
            <Text style={{ fontSize: font.md, fontWeight: font.semibold }}>{word(n.hostname, n.node_id)}</Text>
            {!n.reported ? (
              <P muted small>This machine runs no update service.</P>
            ) : (
              <>
                <Row label="Running version" value={word(n.current_version)} />
                <Row label="Channel" value={word(n.channel)} />
                <Row label="Update state" value={word(n.state)} />
                <Row label="Update on offer" value={offer ?? 'none'} />
                <Row label="Booted slot" value={word(n.rauc.booted_slot)} />
                <Row label="Last result" value={word(n.last_result)} />
              </>
            )}
            {n.rauc.slots.map((sl, i) => (
              <P key={i} muted small>
                Slot {word(sl.bootname ?? sl.name)}: {word(sl.state)}, {word(sl.boot_status)}, version {word(sl.bundle_version)}
              </P>
            ))}
            {offer && canRequest !== 'no' ? (
              <Button testID={`os-ask-${n.node_id}`} label={busy ? 'Sending…' : `Ask to install ${offer}`} disabled={busy} onPress={() => void ask(n.node_id, offer)} />
            ) : null}
          </Card>
        );
      })}
      {history.data && (history.data.events.length > 0 || history.data.requests.length > 0) ? (
        <>
          <H2>History</H2>
          <Card testID="os-history">
            {history.data.events.map((e, i) => (
              <P key={`e${i}`} small>
                {e.node_id}: {e.state === 'rolled_back' ? 'rolled back' : 'committed'} version {word(e.version)}
              </P>
            ))}
            {history.data.requests.map((r) => (
              <P key={r.action_id} small muted>
                Install {word(r.version)} on {word(r.node_id)}: {r.state.replace(/_/g, ' ')}
              </P>
            ))}
          </Card>
        </>
      ) : null}
    </Screen>
  );
}

// ---- System controls ----

const CONTROLS: SystemControlType[] = ['system.restart', 'system.shutdown', 'system.troubleshoot'];

export function SystemControlsScreen() {
  const { api, features, canRequest } = useSignedIn();
  const { actions, reload: reloadHub } = useHubData();
  const [pick, setPick] = useState<{ type: SystemControlType; p: SystemPlanPreview }>();
  const [busy, setBusy] = useState(false);
  const [filed, setFiled] = useState<Action>();
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' | 'warn' }>();
  if (!features.has(OP.systemPlan)) return <Unavailable testID="system-controls" title="System controls" />;
  const live = filed ? ((actions ?? []).find((a) => a.id === filed.id) ?? filed) : undefined;

  async function preview(type: SystemControlType) {
    setBusy(true);
    setMsg(undefined);
    setPick(undefined);
    try {
      const p = await api.systemPlan(type);
      if (p.policy_verdict === 'refused') setMsg({ text: `The hub will not file this now: ${p.reason ?? 'refused by policy'}.`, tone: 'warn' });
      else setPick({ type, p });
    } catch (e) {
      setMsg({ text: requestError(e, `the ${CONTROL_LABEL[type].toLowerCase()} plan`).text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!pick) return;
    setBusy(true);
    try {
      setFiled(await requestSystemControl(api, pick.type, pick.p.plan_sha256));
      setPick(undefined);
      setMsg({ text: 'Request sent. Nothing has happened: it waits in Approvals until an owner decides.', tone: 'ok' });
      await reloadHub();
    } catch (e) {
      setMsg({ text: requestError(e, `the ${CONTROL_LABEL[pick.type].toLowerCase()} request`).text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen testID="system-controls">
      <H1>System controls</H1>
      <P muted>These only ask. You see the plan first, and an owner approves or denies it in Approvals.</P>
      {canRequest === 'no' ? <Notice tone="warn" text="This sign-in may not file requests." /> : null}
      <View style={s.wrap}>
        {CONTROLS.map((c) => (
          <Button key={c} testID={`control-${c}`} variant="secondary" label={CONTROL_LABEL[c]} disabled={busy || canRequest === 'no'} onPress={() => void preview(c)} />
        ))}
      </View>
      {pick ? (
        <Card testID="control-plan">
          <View style={s.wrap}>
            <Badge label={CONTROL_LABEL[pick.type]} tone="info" />
            {pick.p.risk ? <Badge label={pick.p.risk} tone={pick.p.risk === 'destructive' ? 'bad' : 'info'} /> : null}
          </View>
          <P>{pick.p.plan.summary ?? 'The hub sent a plan without a summary.'}</P>
          {(pick.p.plan.warnings ?? []).map((w, i) => (
            <Notice key={i} tone="warn" text={w} />
          ))}
          <Button testID="control-send" label={busy ? 'Sending…' : `Send ${CONTROL_LABEL[pick.type].toLowerCase()} request`} disabled={busy} onPress={() => void send()} />
        </Card>
      ) : null}
      {msg ? <Notice tone={msg.tone} text={msg.text} /> : null}
      {live ? <P small muted>Your request: {live.state.replace(/_/g, ' ')}</P> : null}
    </Screen>
  );
}

// ---- Device info ----

export function DeviceInfoScreen() {
  const { api } = useSignedIn();
  const hub = useLoad(async () => {
    const [inst, nodes] = await Promise.all([api.instance(), api.nodes()]);
    return { inst, node: hubNode(nodes, inst.hub_node_id) };
  }, [api]);
  if (hub.loading) return <Loading what="device info" />;
  const { inst, node: n } = hub.data ?? {};
  return (
    <Screen testID="device-info">
      <H1>About this box</H1>
      {hub.error && !hub.data ? <Failed e={hub.error} forbidden={hub.forbidden} what="device info" /> : null}
      {inst ? (
        <Card>
          <Row label="Name" value={inst.name} />
          <Row label="OneMind version" value={inst.version} />
          {inst.api?.version ? <Row label="API version" value={inst.api.version} /> : null}
        </Card>
      ) : null}
      {n ? (
        <Card testID="device-hardware">
          <Row label="Machine" value={n.hostname} />
          <Row label="Board" value={`${n.board} · ${n.arch}`} />
          <Row label="System" value={n.os.pretty} />
          <Row label="Kernel" value={n.kernel} />
          <Row label="Processor" value={`${n.cpu_model} · ${n.cpus}`} />
          <Row label="Memory" value={gb(n.mem_total_mb)} />
          <Row label="Disk" value={`${n.disk_total_gb.toFixed(0)} GB`} />
          <Row label="Security" value={`TPM ${n.tpm2 ? 'yes' : 'no'} · Secure Boot ${n.secure_boot}`} />
          <Row label="Up for" value={uptimeText(n.uptime_s)} />
          <Row label="Agent" value={n.agent_version} />
        </Card>
      ) : null}
    </Screen>
  );
}

// ---- Live usage ----

function Bar({ value }: { value: number | undefined }) {
  const t = useTheme();
  return (
    <View style={{ height: 6, borderRadius: 3, backgroundColor: t.borderStrong, overflow: 'hidden' }} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(value ?? 0) }}>
      <View style={{ height: 6, width: `${value ?? 0}%`, backgroundColor: value !== undefined && value >= 90 ? t.danger : t.accent }} />
    </View>
  );
}

export function LiveUsageScreen() {
  const { api, features } = useSignedIn();
  const metrics = features.has(OP.nodeMetrics);
  const perApp = features.has(OP.appMetrics);
  const usage = useLoad(async () => {
    const nodes = await api.nodes();
    const m = await Promise.all(nodes.map((n) => (metrics ? api.nodeMetrics(n.node_id).catch(() => undefined) : undefined)));
    const apps = perApp ? (await api.apps()).filter((a) => a.installed) : [];
    const am = await Promise.all(apps.map((a) => api.appMetrics(a.id).catch(() => undefined)));
    return { nodes, m, apps: apps.map((a, i) => ({ id: a.id, name: a.name ?? a.id, m: am[i] as AppMetrics | undefined })) };
  }, [api, metrics, perApp]);
  const summary = useLoad(() => (features.has(OP.monitoringSummary) ? api.monitoringSummary() : Promise.resolve(undefined)), [api, features]);
  if (!metrics && !perApp && !features.has(OP.monitoringSummary)) return <Unavailable testID="live-usage" title="Live usage" />;
  if (usage.loading) return <Loading what="usage" />;
  const d = usage.data;
  return (
    <Screen testID="live-usage">
      <H1>Live usage</H1>
      {usage.error && !d ? <Failed e={usage.error} forbidden={usage.forbidden} what="usage" /> : null}
      {summary.data ? (
        <Card testID="usage-summary">
          <Row label="Machines" value={`${summary.data.nodes.online} online · ${summary.data.nodes.stale} stale · ${summary.data.nodes.offline} offline`} />
          <Row label="Open alerts" value={Object.entries(summary.data.open_alerts).map(([k, v]) => `${v} ${k}`).join(' · ')} />
        </Card>
      ) : null}
      {d?.nodes.map((n, i) => {
        const x = latestSample(d.m[i]);
        const mem = usedPct(x?.mem_used_mb, x?.mem_total_mb) ?? usedPct(n.mem_total_mb - n.mem_available_mb, n.mem_total_mb);
        const diskUsed = x?.disk_total_gb != null && x.disk_free_gb != null ? x.disk_total_gb - x.disk_free_gb : n.disk_total_gb - n.disk_free_gb;
        const disk = usedPct(diskUsed, x?.disk_total_gb ?? n.disk_total_gb);
        return (
          <Card key={n.node_id} testID={`usage-${n.node_id}`}>
            <View style={s.row}>
              <Text style={{ fontSize: font.md, fontWeight: font.semibold }}>{n.hostname}</Text>
              <Badge label={n.status} tone={STATUS_TONE[n.status]} />
            </View>
            <Row label="CPU" value={pct(x?.cpu_pct)} />
            <Bar value={x?.cpu_pct ?? undefined} />
            <Row label="Memory" value={mem === undefined ? 'not reported' : `${pct(mem)} of ${gb(x?.mem_total_mb ?? n.mem_total_mb)}`} />
            <Bar value={mem} />
            <Row label="Disk" value={disk === undefined ? 'not reported' : `${pct(disk)} of ${(x?.disk_total_gb ?? n.disk_total_gb).toFixed(0)} GB`} />
            <Bar value={disk} />
          </Card>
        );
      })}
      {d && d.apps.length > 0 ? <H2>Per app</H2> : null}
      {d?.apps.map((a) => (
        <Card key={a.id} testID={`usage-app-${a.id}`}>
          <Text style={{ fontSize: font.md, fontWeight: font.semibold }}>{a.name}</Text>
          {!a.m || a.m.components.length === 0 ? (
            <P muted small>The hub has no usage numbers for this app.</P>
          ) : (
            a.m.components.map((c) => (
              <Row key={c.name} label={c.name} value={`${c.cpu_millicores === null ? '?' : `${Math.round(c.cpu_millicores)} m`} CPU · ${c.mem_mb === null ? '?' : formatBytes(c.mem_mb * 1e6)}`} />
            ))
          )}
        </Card>
      ))}
    </Screen>
  );
}

// ---- Network (read only) ----

export function NetworkScreen() {
  const { api, features } = useSignedIn();
  const served = features.has(OP.mesh);
  const mesh = useLoad(() => (served ? api.mesh() : Promise.resolve(undefined)), [api, served]);
  if (!served) return <Unavailable testID="network" title="Network" />;
  if (mesh.loading) return <Loading what="network" />;
  const m = mesh.data;
  return (
    <Screen testID="network">
      <H1>Network</H1>
      {mesh.error && !m ? <Failed e={mesh.error} forbidden={mesh.forbidden} what="the network" /> : null}
      {m ? (
        <Card>
          <Row label="Mode" value={m.mode === 'lan' ? 'Home network (LAN)' : m.mode} />
          <Row label="Box name" value={m.box} />
          <Row label="HTTPS" value={m.https ? 'on' : 'off'} />
          {(m.names?.lan ?? []).map((n) => <Row key={n} label="LAN name" value={n} />)}
          {(m.names?.mesh ?? []).map((n) => <Row key={n} label="Mesh name" value={n} />)}
        </Card>
      ) : null}
      <P muted small>Read only. The hub does not report network interfaces, the gateway or DNS servers yet, so they are not shown rather than guessed.</P>
    </Screen>
  );
}
