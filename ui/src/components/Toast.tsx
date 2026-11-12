// SPDX-License-Identifier: Apache-2.0
// Toasts confirm what just happened; they never carry the only copy of important news
// (that goes to the alert centre). Errors stay until closed; others leave after 6 s,
// paused while hovered or focused (WCAG 2.2.1).
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import type { Tone } from '../tokens/tokens';
import { cx } from '../lib/cx';
import { Icon, type IconName } from './Icon';

export interface ToastInput {
  tone?: Tone;
  title: string;
  body?: string;
  /** e.g. "View in Approvals" */
  action?: { label: string; onClick: () => void };
}

interface ToastItem extends ToastInput {
  id: number;
}

interface ToastApi {
  show: (t: ToastInput) => number;
  dismiss: (id: number) => void;
}

const Ctx = createContext<ToastApi | null>(null);

const TONE_ICON: Record<Tone, IconName> = { ok: 'check', warn: 'alert', bad: 'alert', info: 'info', neutral: 'info', agent: 'agent' };
export const TOAST_MS = 6000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const next = useRef(1);

  const dismiss = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) clearTimeout(t);
    timers.current.delete(id);
    setItems((xs) => xs.filter((x) => x.id !== id));
  }, []);

  const arm = useCallback(
    (item: ToastItem) => {
      if (item.tone === 'bad') return;
      timers.current.set(item.id, setTimeout(() => dismiss(item.id), TOAST_MS));
    },
    [dismiss],
  );

  const show = useCallback(
    (t: ToastInput) => {
      const item = { ...t, id: next.current++ };
      setItems((xs) => [...xs.slice(-3), item]);
      arm(item);
      return item.id;
    },
    [arm],
  );

  const pause = (id: number) => {
    const t = timers.current.get(id);
    if (t) clearTimeout(t);
    timers.current.delete(id);
  };

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);
  const urgent = items.filter((i) => i.tone === 'bad');
  const polite = items.filter((i) => i.tone !== 'bad');

  const render = (item: ToastItem) => (
    <div
      key={item.id}
      className={cx('om-toast', `om-tone-${item.tone ?? 'neutral'}`)}
      onMouseEnter={() => pause(item.id)}
      onMouseLeave={() => arm(item)}
      onFocus={() => pause(item.id)}
    >
      <Icon name={TONE_ICON[item.tone ?? 'neutral']} />
      <div className="om-toast-text">
        <p className="om-toast-title">{item.title}</p>
        {item.body && <p className="om-toast-body">{item.body}</p>}
      </div>
      {item.action && (
        <button
          type="button"
          className="om-btn om-btn-ghost om-btn-sm"
          onClick={() => {
            item.action!.onClick();
            dismiss(item.id);
          }}
        >
          {item.action.label}
        </button>
      )}
      <button type="button" className="om-icon-btn" aria-label={`Dismiss: ${item.title}`} onClick={() => dismiss(item.id)}>
        <Icon name="x" size={16} />
      </button>
    </div>
  );

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="om-toasts">
        <div role="status" aria-live="polite" className="om-toast-region">
          {polite.map(render)}
        </div>
        <div role="alert" aria-live="assertive" className="om-toast-region">
          {urgent.map(render)}
        </div>
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(Ctx);
  if (!api) throw new Error('useToast must be used inside <ToastProvider>');
  return api;
}
