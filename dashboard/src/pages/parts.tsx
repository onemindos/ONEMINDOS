// SPDX-License-Identifier: Apache-2.0
// Small shared pieces of the wiring-pass pages: a loader that says what went wrong in words, a
// "show once" secret dialog, and a runner for button actions that reports errors as a toast.
import { useCallback, useState, type ReactNode } from 'react';
import { Button, Dialog, StateView, useToast } from '@onemind/ui';
import { ApiError } from '../api/types';
import type { Polled } from '../lib/hooks';
import { errorText } from '../data/hub';
import { t } from '../i18n';

/** Render a polled resource: loading, a plain-words error (403 says who may see it), or the data. */
export function Load<T>({ res, what, children }: { res: Polled<T>; what: string; children: (data: T) => ReactNode }) {
  if (res.data !== undefined) return <>{children(res.data)}</>;
  if (res.error) {
    const e = res.error;
    if (e.status === 403 || e.code === 'permission_denied') return <p className="om-note om-tone-warn" role="status">{t('error.forbidden')}</p>;
    return (
      <p className="om-note om-tone-bad" role="status">
        {t('error.generic', { message: e.code === 'network' ? 'the hub did not answer' : e.message })}{' '}
        <Button size="sm" variant="ghost" onClick={() => void res.reload()}>
          {t('common.retry')}
        </Button>
      </p>
    );
  }
  return <StateView state="loading" what={what} skeleton="list" />;
}

/** Run a mutation; on failure show why in a toast (never an alert: the screen keeps one at most). */
export function useRun() {
  const toast = useToast();
  return useCallback(
    async <T,>(job: () => Promise<T>, title: string): Promise<T | undefined> => {
      try {
        return await job();
      } catch (e) {
        const { code, message } = errorText(e);
        const stepUp = e instanceof ApiError && e.reason === 'step_up_required';
        toast.show({ tone: 'bad', title, body: stepUp ? 'This needs a fresh passkey sign-in. Sign out and sign in with your passkey, then try again.' : `${message} (${code})` });
        return undefined;
      }
    },
    [toast],
  );
}

/** A secret the hub shows once (API token, invite code). Lives in component state, never storage. */
export function OneTimeDialog({ title, note, secret, onClose }: { title: string; note: string; secret: string | undefined; onClose: () => void }) {
  return (
    <Dialog open={secret !== undefined} onClose={onClose} title={title} description={note} actions={<Button onClick={onClose}>{t('common.close')}</Button>}>
      <code className="dash-secret">{secret}</code>
    </Dialog>
  );
}

/** Tiny controlled-form helper: one string field with a visible label. */
export function TextField({ id, label, value, onChange, type = 'text', autoComplete = 'off' }: { id: string; label: string; value: string; onChange: (v: string) => void; type?: string; autoComplete?: string }) {
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <input id={id} type={type} value={value} autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} />
    </>
  );
}

export function useBusy() {
  const [busy, setBusy] = useState(false);
  return [busy, async (job: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await job();
    } finally {
      setBusy(false);
    }
  }] as const;
}
