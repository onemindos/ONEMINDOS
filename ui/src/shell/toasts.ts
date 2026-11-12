// SPDX-License-Identifier: Apache-2.0
// Shell toasts on top of the library ToastProvider (components/Toast.tsx). Toasts confirm what
// just happened and point to where it lives; the notification centre keeps the copy (P3).
import { useEffect, useRef } from 'react';
import type { Tone } from '../tokens/tokens';
import { useToast, type ToastInput } from '../components/Toast';
import { KIND_META, safeDeepLink, type ShellNotification } from './notifications';

export type Navigate = (href: string) => void;

const SEVERITY_TONE: Record<ShellNotification['severity'], Tone> = { critical: 'bad', warning: 'warn', info: 'info' };

/** A toast for a notification that just arrived. Critical ones use the error tone and stay until closed. */
export function toastForNotification(n: ShellNotification, navigate: Navigate): ToastInput {
  const meta = KIND_META[n.kind];
  const tone: Tone = n.severity === 'critical' ? 'bad' : meta.tone === 'neutral' ? SEVERITY_TONE[n.severity] : meta.tone;
  return {
    tone,
    title: n.title,
    body: n.body,
    action: { label: n.linkLabel ?? meta.link, onClick: () => navigate(safeDeepLink(n.href)) },
  };
}

/** The confirmation after a request is created: it is waiting, not done (P1). */
export function toastForRequest(title: string, actionId: string, navigate: Navigate): ToastInput {
  return {
    tone: 'info',
    title: 'Request sent',
    body: `${title}. It waits in Approvals until the owner decides.`,
    action: { label: 'View', onClick: () => navigate(`#/approvals/${encodeURIComponent(actionId)}`) },
  };
}

/** A request could not be created: say the contract error and keep the toast until closed. */
export function toastForRequestError(title: string, code: string, message: string): ToastInput {
  return { tone: 'bad', title: `Could not request: ${title}`, body: `${message} (${code})` };
}

/** Ids that are new since the last call, newest list wins; the first call only records. */
export function newArrivals(seen: Set<string> | null, items: ShellNotification[]): { fresh: ShellNotification[]; seen: Set<string> } {
  const next = new Set(items.map((n) => n.id));
  if (seen === null) return { fresh: [], seen: next };
  return { fresh: items.filter((n) => !seen.has(n.id) && !n.read), seen: next };
}

/**
 * Show a toast for each unread notification that arrives after mount (at most 3 at once, so a
 * reconnect after hours offline does not flood the screen; the centre still has all of them).
 */
export function useNotificationToasts(items: ShellNotification[], navigate: Navigate, max = 3): void {
  const toast = useToast();
  const seen = useRef<Set<string> | null>(null);
  const nav = useRef(navigate);
  nav.current = navigate;
  useEffect(() => {
    const { fresh, seen: next } = newArrivals(seen.current, items);
    seen.current = next;
    const shown = fresh.slice(0, max);
    for (const n of shown) toast.show(toastForNotification(n, (h) => nav.current(h)));
    if (fresh.length > max) {
      toast.show({ tone: 'info', title: `${fresh.length - max} more notifications`, action: { label: 'Open', onClick: () => nav.current('#/notifications') } });
    }
  }, [items, toast, max]);
}
