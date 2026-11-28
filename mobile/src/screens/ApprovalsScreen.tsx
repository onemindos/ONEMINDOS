// SPDX-License-Identifier: Apache-2.0
import { useContext, useLayoutEffect, useRef, useState } from 'react';
import { SafeAreaView } from 'react-native-safe-area-context';
import { NavigationContext, NavigationRouteContext } from '@react-navigation/native';
import type { TabParams } from '../nav';
import type { components } from '@onemind/sdk';
import { OP, type OneMindApi } from '../api/client';
import { HoldButton, requiresHold } from '../ui/HoldButton';
import { approvalKeyNative, type ApprovalKeyNative } from '../../modules/onemind-approval-key';
import { forget } from '../approvalKey';
import { ApprovalKeySection, useApprovalKey } from '../approvalKey/ApprovalKeySection';
import { Pressable, Text, View } from 'react-native';
import type { Action, ApproveBody, Risk } from '../api/types';
import { useHubData, useNow } from '../data';
import { actionTitle, decide, isPending, keyCovers, principalLabel, sortByRecent, type Decision, type StepUp } from '../lib/approvals';
import { platformPasskeys } from '../lib/passkeys';
import { formatAgo, secondsSince } from '../lib/time';
import { summarizeAgents } from '../lib/people';
import { useSignedIn, type Ability } from '../session';
import { Badge, Button, Card, H1, Loading, Notice, P, Row, Screen, StateBadge, s, type Tone } from '../ui/bits';
import { font, space, touchTarget, useTheme } from '../ui/theme';

const RISK_TONE: Record<Risk, Tone> = { read: 'neutral', write: 'info', sensitive: 'warn', destructive: 'bad', actuate: 'bad' };

const SYSTEM_TITLES: Record<string, string> = {
  'system.restart': 'Restart the box',
  'system.shutdown': 'Shut down the box',
  'system.factory_reset': 'Factory reset the box',
};

function requestTitle(a: Action): string {
  return a.plan?.summary || (Object.hasOwn(SYSTEM_TITLES, a.type) ? SYSTEM_TITLES[a.type]! : actionTitle(a));
}

const SEGMENTS = ['Waiting', 'Decided', 'Agents'] as const;
type Segment = (typeof SEGMENTS)[number];

function riskLabel(a: Action) {
  if (a.risk === 'actuate' || (typeof a.approval === 'object' && a.approval?.physical)) return 'Moves a device';
  if (a.risk === 'destructive') return 'Cannot be undone';
  return a.risk && Object.hasOwn(RISK_TONE, a.risk) ? 'Can be undone' : 'Risk unknown';
}

function durationLabel(a: Action) {
  const planParams = a.plan && 'params' in a.plan ? a.plan.params : undefined;
  for (const source of [a.plan, planParams, a.params]) {
    if (!source || typeof source !== 'object') continue;
    const values = Object.entries(source);
    const minutes = values.find(([key]) => key === 'duration_min' || key === 'duration_minutes')?.[1];
    if (typeof minutes === 'number' && Number.isFinite(minutes) && minutes > 0) return `${minutes} min`;
    const seconds = values.find(([key]) => key === 'duration_s' || key === 'duration_seconds')?.[1];
    if (typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0) {
      return seconds % 60 === 0 ? `${seconds / 60} min` : `${seconds} s`;
    }
  }
  return undefined;
}

function expiryText(expiresAt: string, now: number) {
  const remaining = Date.parse(expiresAt) - now;
  if (!Number.isFinite(remaining)) return 'Expiry unavailable';
  if (remaining <= 0) return 'Expired';
  if (remaining < 60_000) return 'Less than 1 min left. If nobody answers, nothing is approved.';
  return `${Math.floor(remaining / 60_000)} min left. If nobody answers, nothing is approved.`;
}

/** `sha256:9a1e5c…8f7a`: enough to compare with the dashboard or CLI, short enough to read. */
export function shortHash(h: string | null | undefined): string | undefined {
  if (!h) return undefined;
  const [alg, hex] = h.includes(':') ? h.split(':', 2) : ['sha256', h];
  return hex && hex.length > 14 ? `${alg}:${hex.slice(0, 6)}…${hex.slice(-4)}` : h;
}

function List({ label, items }: { label: string; items: unknown[] | undefined }) {
  const t = useTheme();
  if (!items?.length) return null;
  return (
    <View style={{ gap: 2 }}>
      <Text style={{ color: t.muted, fontSize: 12 }}>{label}</Text>
      {items.slice(0, 8).map((x, i) => (
        <Text key={i} style={{ color: t.text, fontSize: 13 }}>
          • {typeof x === 'string' ? x : JSON.stringify(x)}
        </Text>
      ))}
      {items.length > 8 && <Text style={{ color: t.muted, fontSize: 12 }}>and {items.length - 8} more</Text>}
    </View>
  );
}

/** §12.4 plan: what will actually run. The approval is bound to its hash. */
function PlanBlock({ a, details }: { a: Action; details: boolean }) {
  const t = useTheme();
  const p = a.plan;
  const evidence = typeof a.approval === 'object' ? a.approval : undefined;
  const warnings = p?.warnings ?? [];
  const rollbackAt = p && 'rollback_at' in p && typeof p.rollback_at === 'string' ? new Date(p.rollback_at) : undefined;
  const rollback = rollbackAt && Number.isFinite(rollbackAt.getTime()) ? rollbackAt.toLocaleString() : undefined;
  if (!details && !evidence?.preview?.text && !evidence?.limits?.length && !warnings.length && !rollback) return null;
  return (
    <View testID={`plan-${a.id}`} style={{ gap: space.sm, borderTopWidth: 1, borderTopColor: t.border, paddingTop: space.sm }}>
      <Text style={{ color: t.text, fontWeight: '600' }}>What will happen</Text>
      {rollback && <Row label="Goes back at" value={rollback} />}
      {evidence?.preview?.text && <P small>{evidence.preview.text}</P>}
      {!!evidence?.limits?.length && (
        <List label="Limits" items={evidence.limits.map(({ name, value, unit }) => `${name} · ${value}${unit ? ` ${unit}` : ''}`)} />
      )}
      {warnings.map((w, i) => <Notice key={i} tone="warn" text={w} />)}
      {details && (
        <>
          <List label="Images" items={p?.images} />
          <List label="Storage" items={p?.volumes} />
          <List label="Machines" items={p?.nodes} />
          <List label="Objects" items={p?.objects} />
          {a.plan_sha256 && <Row label="Plan" value={shortHash(a.plan_sha256)} />}
          <View style={{ backgroundColor: t.neutralBg, borderRadius: 8, padding: space.md }}>
            <P muted small>Exact request</P>
            <Text testID={`params-${a.id}`} style={{ color: t.text, fontFamily: 'monospace', fontSize: 13 }}>
              {exactParams(a)}
            </Text>
          </View>
        </>
      )}
    </View>
  );
}

/** The requester's own words. From an agent this is untrusted text, so it is labelled as such. */
function ReasonBlock({ a }: { a: Action }) {
  const t = useTheme();
  if (!a.reason) return null;
  const agent = a.requested_by?.kind === 'agent';
  return (
    <View testID={`reason-${a.id}`} style={{ backgroundColor: agent ? t.agentBg : t.neutralBg, borderRadius: 8, padding: space.md, gap: 4 }}>
      <Text style={{ color: agent ? t.agent : t.muted, fontSize: 12, fontWeight: '600' }}>
        {agent ? 'Reason given by the agent (its words, not checked by the hub)' : 'Reason given'}
      </Text>
      <Text style={{ color: t.text, fontSize: 14 }}>{a.reason}</Text>
    </View>
  );
}

/** The exact request, as the hub stores it: what is approved is what runs. */
export function exactParams(a: Action): string {
  return JSON.stringify({ type: a.type, params: a.params }, null, 2);
}

function PendingCard({
  a,
  now,
  canDecide,
  busy,
  offline,
  keyed,
  expanded,
  onExpand,
  canSign,
  hasCredential,
  onDecide,
}: {
  a: Action;
  now: number;
  canDecide: Ability;
  busy: boolean;
  offline: boolean;
  keyed: boolean;
  expanded: boolean;
  onExpand: () => void;
  canSign: boolean;
  hasCredential: boolean;
  onDecide: (a: Action, d: Decision, holdMs?: number) => void;
}) {
  const t = useTheme();
  const [details, setDetails] = useState(false);
  const expires = Date.parse(a.expires_at);
  const expired = !Number.isFinite(expires) || expires <= now;
  const hold = requiresHold(a);
  const off = busy || canDecide === 'no' || expired || offline;
  const isAgent = a.requested_by?.kind === 'agent';
  const title = requestTitle(a);
  const risk = riskLabel(a);
  const duration = durationLabel(a);
  const tone = a.risk ? RISK_TONE[a.risk] : 'neutral';
  if (!expanded) {
    return (
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} accessibilityLabel={`Review ${title}`}
        onPress={onExpand} testID={`expand-${a.id}`}>
        <Card testID={`pending-${a.id}`}>
          <P>{title} ›</P>
          <P muted small>{risk}</P>
        </Card>
      </Pressable>
    );
  }
  return (
    <Card testID={`pending-${a.id}`}>
      <View style={[s.row, { flexWrap: 'wrap' }]}>
        <View style={{ flexShrink: 1 }}>
          <P>{a.requested_by ? `${a.requested_by.id} asks` : 'Requester unavailable'}</P>
          {isAgent && <P muted small>AI agent · can ask, cannot act</P>}
        </View>
        <Badge label={`${hold ? '◆' : '○'} ${risk}`} tone={tone ?? 'neutral'} />
      </View>
      <Text accessibilityRole="header" style={{ color: t.text, fontSize: 22, fontWeight: font.bold }}>{title}</Text>
      <P muted small>Asked {formatAgo(secondsSince(a.created_at ?? '', now))}</P>
      <ReasonBlock a={a} />
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: details }} testID={`details-${a.id}`}
        onPress={() => setDetails(!details)} style={{ minHeight: touchTarget, justifyContent: 'center' }}>
        <Text style={{ color: t.accent, fontSize: font.sm, fontWeight: font.semibold }}>{details ? 'Hide request details' : 'Review request details'}</Text>
      </Pressable>
      <PlanBlock a={a} details={details} />
      {canDecide !== 'no' && canSign && keyed && (
        <P muted small>{keyCovers(a)
          ? "This phone's approval key signs after you confirm with your fingerprint or face. A PIN is not accepted."
          : 'This request may ask for your passkey instead of the approval key. Physical actions always take the passkey.'}</P>
      )}
      {canDecide !== 'no' && canSign && !hasCredential && <Notice text="Add a passkey to approve from this phone." />}
      <View style={{ gap: space.sm }}>
        {hold ? (
          <HoldButton key={`${a.updated_at}:${a.plan_sha256}`} testID={`approve-${a.id}`}
            label={duration ? `Hold to approve ${duration}` : 'Hold to approve'} disabled={off || !canSign || !hasCredential}
            onComplete={(holdMs) => onDecide(a, 'approve', holdMs)} />
        ) : (
          <Button testID={`approve-${a.id}`} label={keyed && keyCovers(a) ? 'Approve with biometrics' : 'Approve with passkey'}
            disabled={off || !canSign || !hasCredential} onPress={() => onDecide(a, 'approve')} />
        )}
        <Button testID={`deny-${a.id}`} label="Deny" variant="secondary" disabled={off} onPress={() => onDecide(a, 'deny')} />
      </View>
      <P muted small>{expiryText(a.expires_at, now)}</P>
    </Card>
  );
}

export function ApprovalsScreen({ keyNative = approvalKeyNative }: { keyNative?: ApprovalKeyNative } = {}) {
  const now = useNow();
  const t = useTheme();
  const { api, canDecide, markForbidden, features, me, connection } = useSignedIn();
  const { actions, hubOffsetMs, loading, reload, error } = useHubData();
  const nav = useContext(NavigationContext);
  useLayoutEffect(() => nav?.setOptions({ headerShown: false }), [nav]);
  const route = useContext(NavigationRouteContext);
  const { id: reviewId, reviewKey } = (route?.params as TabParams['Approvals']) ?? {};
  const deciding = useRef(false);
  const [busy, setBusy] = useState<string>();
  const [msg, setMsg] = useState<{ text: string; ok: boolean }>();
  const hubNow = now + (hubOffsetMs ?? 0);
  const [selection, setSelection] = useState<{ reviewId?: string; reviewKey?: number; segment: Segment; id?: string }>();
  const canSign = features.has(OP.approveOptions);
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;
  const key = useApprovalKey(keyNative, hubUrl);
  const hasCredential = (me?.passkeys ?? 0) > 0 || !!key.signer;
  const ctx: StepUp = { features, passkeys: platformPasskeys(), ownerHasPasskey: true, hubUrl, approvalKey: key.signer };

  async function onDecide(a: Action, d: Decision, holdMs?: number) {
    if (deciding.current || error || canDecide === 'no' || !(Date.parse(a.expires_at) > Date.now() + (hubOffsetMs ?? 0))) return;
    if (d === 'approve' && (!canSign || !hasCredential || (requiresHold(a) && holdMs === undefined))) return;
    // The gateway requires the hold duration alongside the signed approval. Leave the challenge,
    // plan binding and signer untouched. Only decorate the final write after the completed hold.
    const decisionApi = holdMs === undefined ? api : Object.assign(Object.create(api) as OneMindApi, {
      approveOptions: api.approveOptions.bind(api),
      approve(id: string, body?: ApproveBody) {
        const request = { ...body, hold_ms: holdMs } satisfies ApproveBody &
          Pick<components['schemas']['onemind_core__routers__actions__ApproveBody'], 'hold_ms'>;
        return api.approve(id, request);
      },
    });
    deciding.current = true;
    setBusy(a.id);
    setMsg(undefined);
    const r = await decide(decisionApi, a, d, ctx);
    if (!r.ok && r.forbidden) markForbidden();
    // A new fingerprint or face killed the key: revoke it on the hub (best effort) and offer set-up again.
    if (!r.ok && r.reason === 'invalidated' && key.rec) {
      await forget(api, key.rec, keyNative).catch(() => undefined);
      key.set(null);
    }
    setMsg({ text: r.message, ok: r.ok });
    await reload();
    deciding.current = false;
    setBusy(undefined);
  }

  if (loading && !actions) return <Loading what="requests" />;
  const latest = sortByRecent(actions ?? []);
  const pending = latest.filter(isPending);
  const review = pending.find((a) => a.id === reviewId);
  const visible = review ? [review, ...pending.filter((a) => a.id !== reviewId)] : pending;
  const currentSelection = selection?.reviewId === reviewId && selection?.reviewKey === reviewKey ? selection : undefined;
  const selectedId = currentSelection?.id;
  const expandedId = visible.find((a) => a.id === selectedId)?.id ?? (reviewId ? review?.id : visible[0]?.id);
  const selectedSegment = currentSelection?.segment ?? 'Waiting';
  const decided = latest.filter((a) => !isPending(a) && a.state !== 'requested');
  const agents = summarizeAgents(latest, undefined);

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1 }}>
      <Screen key={reviewKey ?? reviewId} testID="approvals">
        <H1>Approvals</H1>
        <View accessibilityRole="tablist" style={{
          flexDirection: 'row', padding: 2, borderRadius: 12, borderWidth: 1, borderColor: t.border, backgroundColor: t.sunken,
        }}>
          {SEGMENTS.map((tab) => (
            <Pressable key={tab} testID={`segment-${tab}`} accessibilityRole="tab"
              accessibilityState={{ selected: selectedSegment === tab }}
              onPress={() => setSelection({ reviewId, reviewKey, segment: tab, id: expandedId })}
              style={{ flex: 1, minHeight: touchTarget, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
                backgroundColor: selectedSegment === tab ? t.card : t.sunken }}>
              <Text style={{ fontSize: font.sm, fontWeight: font.semibold, color: selectedSegment === tab ? t.accent : t.muted }}>
                {tab === 'Waiting' ? `Waiting · ${pending.length}` : tab}
              </Text>
            </Pressable>
          ))}
        </View>
        {msg && <Notice tone={msg.ok ? 'ok' : 'bad'} text={msg.text} />}
        {selectedSegment === 'Waiting' && (
          <>
            {reviewId && !review && <Notice text="This request is no longer waiting for approval." />}
            {canDecide === 'no' && <Notice tone="warn" text="You can see requests, but only an owner can approve or deny them." />}
            {canDecide === 'unknown' && <Notice text="The hub checks that you are an owner when you approve or deny." />}
            {error && <Notice tone="warn" text="The hub is unreachable. Approvals and denials are disabled." />}
            {canDecide !== 'no' && !canSign && !!pending.length && <Notice text="This hub cannot sign phone approvals." />}
            {!visible.length && <P muted>Nothing is waiting.</P>}
            {visible.map((a) => (
              <PendingCard key={a.id} a={a} now={hubNow} canDecide={canDecide} busy={busy !== undefined} offline={!!error}
                keyed={!!key.signer} canSign={canSign} hasCredential={hasCredential} expanded={a.id === expandedId}
                onExpand={() => setSelection({ reviewId, reviewKey, segment: 'Waiting', id: a.id })}
                onDecide={(x, d, holdMs) => void onDecide(x, d, holdMs)} />
            ))}
            <ApprovalKeySection api={api} features={features} native={keyNative} hubUrl={hubUrl} state={key} owner={canDecide !== 'no'} />
          </>
        )}
        {selectedSegment === 'Decided' && (
          <>
            {!decided.length && <P muted>No decided requests.</P>}
            {decided.map((a) => (
              <Card key={a.id} testID={`decided-${a.id}`}>
                <P>{requestTitle(a)}</P>
                <StateBadge state={a.state} />
                {a.decided_by && <Row label="Decided by" value={principalLabel(a.decided_by)} />}
                <P muted small>Updated {formatAgo(secondsSince(a.updated_at ?? a.decided_at ?? '', hubNow))}</P>
              </Card>
            ))}
          </>
        )}
        {selectedSegment === 'Agents' && (
          <>
            {!agents.length && <P muted>No agent requests.</P>}
            {agents.map((agent) => (
              <Card key={agent.id} testID={`approval-agent-${agent.id}`}>
                <P>{agent.id}</P>
                <P muted small>{agent.asks} requests · {agent.waiting} waiting</P>
                {agent.last && <P muted small>Last asked {formatAgo(secondsSince(agent.last, hubNow))}</P>}
              </Card>
            ))}
          </>
        )}
      </Screen>
    </SafeAreaView>
  );
}
