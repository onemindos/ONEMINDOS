// SPDX-License-Identifier: Apache-2.0
// Automation (contract §12.17): the rules, the kill switch and what fired. A rule can only REQUEST actions;
// every request it files still waits for approval (or an owner's standing approval) like any other.
// Turning things OFF (disable, pause) is one tap. Turning things ON (enable, resume) is owner only and asks
// twice. Creating or editing rules stays on the dashboard.
import { useState } from 'react';
import { Text, View } from 'react-native';
import type { AutomationRule } from '../api/types';
import { requestError } from '../lib/manage';
import { useLoad } from '../lib/useLoad';
import { formatAgo, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';
import { Badge, Button, Card, H1, H2, Loading, Notice, P, Row, Screen, s } from '../ui/bits';
import { font, useTheme } from '../ui/theme';

export function triggerText(r: Pick<AutomationRule, 'trigger'>): string {
  const t = r.trigger ?? {};
  const sch = t.schedule as { cron?: string; tz?: string } | undefined;
  if (sch) return `on a schedule (${sch.cron ?? '?'}${sch.tz ? `, ${sch.tz}` : ''})`;
  const ev = t.event as { type?: string } | undefined;
  if (ev) return `when ${ev.type ?? 'an event'} happens`;
  if (t.webhook) return 'on a webhook';
  if (t.manual) return 'by hand';
  return 'unknown trigger';
}

export function AutomationScreen() {
  const t = useTheme();
  const { api, canDecide } = useSignedIn();
  const state = useLoad(() => api.automationState(), [api]);
  const rules = useLoad(() => api.automationRules(), [api]);
  const runs = useLoad(() => api.automationRuns().catch(() => []), [api]);
  const [armed, setArmed] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; tone: 'ok' | 'bad' }>();
  const [denied, setDenied] = useState(false);

  if (rules.loading || state.loading) return <Loading what="automation" />;
  const mayWrite = canDecide !== 'no' && !denied;
  const paused = !!state.data?.paused;

  async function act(key: string, fn: () => Promise<unknown>, done: string, safe: boolean) {
    // Anything that turns something on needs a second tap that names the consequence.
    if (!safe && armed !== key) {
      setArmed(key);
      return;
    }
    setArmed(undefined);
    setBusy(true);
    setMsg(undefined);
    try {
      await fn();
      setMsg({ text: done, tone: 'ok' });
      await Promise.all([state.reload(), rules.reload()]);
    } catch (e) {
      const r = requestError(e, 'that change');
      if (r.forbidden) setDenied(true);
      setMsg({ text: r.text, tone: 'bad' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen testID="automation">
      <H1>Automation</H1>
      {rules.error && !rules.data ? <Notice tone={rules.forbidden ? 'warn' : 'bad'} text={rules.forbidden ? 'This sign-in may not read automation.' : `Could not read automation: ${rules.error.message}`} /> : null}
      <Card testID="automation-state">
        <View style={s.wrap}>
          <Badge label={paused ? 'Paused' : 'Running'} tone={paused ? 'warn' : 'ok'} />
        </View>
        <P muted small>
          {paused
            ? 'Rules do not fire while paused. Nothing is filed on its own.'
            : 'Rules can only ask. Each request they file waits for approval like any other.'}
        </P>
        {state.data?.reason ? <Row label="Reason" value={state.data.reason} /> : null}
        <View style={s.wrap}>
          {paused ? (
            <Button
              testID="resume"
              label={armed === 'resume' ? 'Tap again: let rules fire again' : 'Resume'}
              disabled={busy || !mayWrite}
              onPress={() => void act('resume', () => api.setAutomationPaused(false), 'Automation resumed.', false)}
            />
          ) : (
            <Button
              testID="pause"
              variant="secondary"
              label="Pause all rules"
              disabled={busy || !mayWrite}
              onPress={() => void act('pause', () => api.setAutomationPaused(true, 'Paused from the phone'), 'Automation paused.', true)}
            />
          )}
        </View>
      </Card>
      <H2>Rules</H2>
      {(rules.data ?? []).length === 0 ? (
        <P muted>No rules yet.</P>
      ) : (
        (rules.data ?? []).map((r) => (
          <Card key={r.id} testID={`rule-${r.id}`}>
            <View style={s.row}>
              <Text style={{ color: t.text, fontSize: font.md, fontWeight: font.semibold, flexShrink: 1 }}>{r.name}</Text>
              <Badge label={r.enabled ? 'on' : 'off'} tone={r.enabled ? 'ok' : 'neutral'} />
            </View>
            <P muted small>
              {triggerText(r)}
              {r.last_fired_at ? `; last fired ${formatAgo(secondsSince(r.last_fired_at, Date.now()))}` : '; never fired'}
            </P>
            {r.breaker === 'open' ? <Notice tone="warn" text="This rule stopped itself after repeated failures." /> : null}
            {!r.system && (
              <View style={s.wrap}>
                {r.enabled ? (
                  <Button
                    testID={`disable-${r.id}`}
                    variant="secondary"
                    label="Turn off"
                    disabled={busy || !mayWrite}
                    onPress={() => void act(`d-${r.id}`, () => api.setRuleEnabled(r.id, false), `${r.name} is off.`, true)}
                  />
                ) : (
                  <Button
                    testID={`enable-${r.id}`}
                    label={armed === `e-${r.id}` ? 'Tap again: this rule may start asking' : 'Turn on'}
                    disabled={busy || !mayWrite}
                    onPress={() => void act(`e-${r.id}`, () => api.setRuleEnabled(r.id, true), `${r.name} is on. Its requests still wait for approval.`, false)}
                  />
                )}
              </View>
            )}
          </Card>
        ))
      )}
      {!mayWrite && <P muted small>Only an owner can change rules.</P>}
      {msg && <Notice tone={msg.tone} text={msg.text} />}
      <H2>Recent runs</H2>
      {(runs.data ?? []).length === 0 ? (
        <P muted>Nothing has fired yet.</P>
      ) : (
        (runs.data ?? []).slice(0, 8).map((r) => (
          <Row key={r.id} label={r.fired_at ? formatAgo(secondsSince(r.fired_at, Date.now())) : 'unknown'} value={`${r.outcome ?? 'unknown'}${r.action_ids?.length ? `, ${r.action_ids.length} request(s)` : ''}`} />
        ))
      )}
      <P muted small>New rules and edits are made on the dashboard.</P>
    </Screen>
  );
}
