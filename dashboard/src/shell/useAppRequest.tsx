// SPDX-License-Identifier: Apache-2.0
// A preview is read-only. Filing its fingerprint still requires a separate human approval.
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { Button, Dialog, useToast } from '@onemind/ui';
import { useSignedIn } from '../session';
import { errorText, useHub } from '../data/hub';
import type { ActionType, AppParams, PlanPreview } from '../api/types';

export function useAppRequest() {
  const { api } = useSignedIn();
  const hub = useHub();
  const toast = useToast();
  const route = useLocation().key;
  const generation = useRef(0);
  const locked = useRef(false);
  const cancel = useRef<(() => void) | undefined>(undefined);
  const [review, setReview] = useState<{ plan: PlanPreview; summary: string; decide: (yes: boolean) => void }>();
  const invalidate = () => { generation.current++; locked.current = false; cancel.current?.(); cancel.current = undefined; };
  const invalidateRef = useRef(invalidate);
  invalidateRef.current = invalidate;
  useEffect(() => {
    setReview(undefined);
    return () => invalidateRef.current();
  }, [route]);
  const requestApp = async (type: ActionType, appId: string, extra: Omit<AppParams, 'app_id'> = {}) => {
    if (locked.current || hub.canRequest === 'no') return undefined;
    locked.current = true;
    const version = generation.current;
    try {
      const params = { ...extra, app_id: appId };
      if (!api.appPlan || !api.previewAction) throw new Error('This gateway client cannot preview app requests.');
      const plan = type === 'app.install' ? await api.appPlan(appId) : await api.previewAction(type, params);
      if (version !== generation.current) return undefined;
      if (!plan.plan_sha256 || typeof plan.plan?.summary !== 'string' || plan.app_id !== appId || plan.type !== type) throw new Error('The gateway did not return a reviewable plan for this app.');
      if (plan.policy_verdict !== 'needs_approval') throw new Error(plan.reason || 'The gateway refused this request.');
      const summary = plan.plan.summary;
      const confirmed = await new Promise<boolean>((resolve) => {
        cancel.current = () => resolve(false);
        setReview({ plan, summary, decide: resolve });
      });
      if (version !== generation.current) return undefined;
      cancel.current = undefined;
      setReview(undefined);
      if (!confirmed) return undefined;
      const action = await hub.request(type, appId, extra, plan.plan_sha256);
      toast.show({ tone: 'info', title: 'Request sent', body: 'It waits in Approvals until the owner decides.' });
      return action.id;
    } catch (e) {
      if (version === generation.current) toast.show({ tone: 'bad', title: 'Could not request change', body: errorText(e).message });
      return undefined;
    } finally {
      if (version === generation.current) locked.current = false;
    }
  };
  const reviewDialog = review && <Dialog open title="Review app request" onClose={() => review.decide(false)} actions={<><Button onClick={() => review.decide(false)}>Cancel</Button><Button variant="primary" onClick={() => review.decide(true)}>Send request</Button></>}>
    <p>{review.summary}</p>
    <pre>{JSON.stringify(review.plan.plan, null, 2)}</pre>
    <p className="om-hint">Nothing runs now. An owner must approve this exact plan in Approvals.</p>
  </Dialog>;
  return { requestApp, reviewDialog };
}
