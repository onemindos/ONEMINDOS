// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { approvalKeyNative } from '../../modules/onemind-approval-key';
import { forget } from '../approvalKey';
import { useApprovalKey } from '../approvalKey/ApprovalKeySection';
import { OP } from '../api/client';
import type { Action, PlanPreview } from '../api/types';
import { useHubData } from '../data';
import { decide, keyCovers, principalLabel, type Decision } from '../lib/approvals';
import { platformPasskeys } from '../lib/passkeys';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Button, Card, Notice, P, s } from '../ui/bits';
import { requiresHold } from '../ui/HoldButton';
import { font, space, useTheme } from '../ui/theme';

const STEPS = ['Asked', 'Checked', 'You', 'Install'] as const;

export function AppInstallWaiting({ action, now, blocked, onDecision }: {
  action: Action;
  now: number;
  blocked?: string;
  onDecision: (answer: Action, label: string) => void;
}) {
  const t = useTheme();
  const { api, canDecide, markForbidden, connection, features, me, principal } = useSignedIn();
  const { reload, error } = useHubData();
  const [msg, setMsg] = useState<string>();
  const [review, setReview] = useState<PlanPreview['plan']>();
  const [busy, setBusy] = useState(false);
  const working = useRef(false);
  const hubUrl = connection.mode === 'live' ? connection.hubUrl : undefined;
  const key = useApprovalKey(approvalKeyNative, hubUrl);
  const passkeys = platformPasskeys();
  const ownsRequest = principal?.kind === 'person' && action.requested_by?.kind === 'person' && principal.id === action.requested_by.id;
  const denyLabel = ownsRequest ? 'Cancel request' : 'Deny';
  const canReview = !!action.plan || features.has(OP.appPlan);
  const canAct = canDecide === 'yes' && !error && Date.parse(action.expires_at) > now;
  const needsHold = requiresHold(action);
  const keyed = !!key.signer && keyCovers(action);
  const canUsePasskey = (me?.passkeys ?? 0) > 0 && !!passkeys?.supported();
  const canApprove = canAct && !blocked && !needsHold && features.has(OP.approveOptions) && !!action.plan_sha256 &&
    (keyed || canUsePasskey);
  const isUpdate = action.type === 'app.update';

  async function readPlan() {
    const appId = action.params.app_id;
    if (!appId || working.current || !canReview || canDecide !== 'yes') return;
    if (review) return setReview(undefined);
    setMsg(undefined);
    working.current = true;
    setBusy(true);
    try {
      const preview = features.has(OP.appPlan) ? await api.appPlan(appId, isUpdate ? 'app.update' : 'app.install') : undefined;
      if (action.plan_sha256 && preview?.plan_sha256 === action.plan_sha256 && preview.plan) setReview(preview.plan);
      else if (action.plan) setReview(action.plan);
      else setMsg('The hub’s current preview differs from this request. Review the request in Approvals.');
    } catch {
      if (action.plan) setReview(action.plan);
      else setMsg('The plan could not be read from the hub.');
    } finally {
      working.current = false;
      setBusy(false);
    }
  }

  async function send(decision: Decision) {
    if (working.current || !canAct || (decision === 'approve' && !canApprove)) return;
    working.current = true;
    setBusy(true);
    setMsg(undefined);
    try {
      const result = await decide(api, action, decision, { features, passkeys, ownerHasPasskey: true, hubUrl, approvalKey: key.signer });
      if (result.ok) {
        const label = decision === 'deny' && result.action.state === 'cancelled'
          ? ownsRequest ? 'Request cancelled' : 'Request denied'
          : 'Hub response';
        onDecision(result.action, label);
      } else {
        if (result.forbidden) markForbidden();
        if (result.reason === 'invalidated' && key.rec && approvalKeyNative) {
          await forget(api, key.rec, approvalKeyNative).catch(() => undefined);
          key.set(null);
        }
        setMsg(result.message);
      }
      await reload();
    } finally {
      working.current = false;
      setBusy(false);
    }
  }

  return (
    <Card testID="app-install-waiting">
      <Text accessibilityRole="header" style={{ color: t.text, fontSize: font.lg, fontWeight: font.bold }}>◆ {canDecide === 'yes' ? 'Waiting for your approval' : 'Waiting for owner approval'}</Text>
      <P muted small>{ownsRequest ? 'You' : principalLabel(action.requested_by)} asked {formatAgo(secondsSince(action.created_at ?? '', now))}.</P>
      <View accessibilityLabel={`Asked and checked. Waiting for approval before ${isUpdate ? 'update' : 'install'}.`} style={[s.row, { gap: space.xs }]}>
        {STEPS.map((step, i) => (
          <View key={step} style={{ flex: 1, gap: space.xs }} accessible={false}>
            <View style={{ height: 4, borderRadius: 2, backgroundColor: i === 2 ? t.action : i < 2 ? t.ok : t.borderStrong }} />
            <Text style={{ color: t.text, fontSize: font.xs }}>{i < 2 ? '✓ ' : i === 2 ? '◆ ' : ''}{i === 3 && isUpdate ? 'Update' : step}</Text>
          </View>
        ))}
      </View>
      {canAct && !needsHold && features.has(OP.approveOptions) && !blocked && !keyed && !canUsePasskey &&
        <P small muted>Add a passkey to approve from this phone.</P>}
      {canApprove && <Button testID="app-approve" label={keyed ? 'Approve with biometrics' : 'Approve with passkey'}
        disabled={busy} onPress={() => void send('approve')} />}
      {canAct && (
        <View style={s.wrap}>
          {canReview && <Button testID="app-review-plan" variant="secondary" label={review ? 'Hide plan' : 'Review plan'}
            disabled={busy} onPress={() => void readPlan()} />}
          <Button testID="app-deny" variant="secondary" label={denyLabel} disabled={busy} onPress={() => void send('deny')} />
        </View>
      )}
      {review && <Card testID="app-review-plan-content">
        {review.summary && <P>{review.summary}</P>}
        {(review.warnings ?? []).map((warning, i) => <Notice key={i} tone="warn" text={warning} />)}
        <Text selectable style={{ color: t.muted, fontFamily: 'monospace', fontSize: font.xs }}>{JSON.stringify({ type: action.type, params: action.params, plan: review }, null, 2)}</Text>
      </Card>}
      {msg && <Notice tone="bad" text={msg} />}
      {blocked && <P small muted>{blocked}</P>}
      {canAct && needsHold && <P small muted>Open Approvals to review and hold to approve this request.</P>}
      {!needsHold && !isUpdate && <P small muted>No hold here. An install can be undone and moves nothing. Approval still requires a signature.</P>}
    </Card>
  );
}
