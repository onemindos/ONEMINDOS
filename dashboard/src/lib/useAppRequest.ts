// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { ApiError, type CatalogApp } from '../api/types';
import { useSignedIn } from '../session';
import { uuidv4 } from './uuid';

/** How long an owner has to approve a request made from the Market. */
export const REQUEST_TTL_MS = 60 * 60 * 1000;

/**
 * Install/Remove → a §3 action, then to Approvals. Shared by the Market grid and the app page.
 * One idempotency key per (type, app) until the hub gives a definite answer, so retrying after
 * a lost response returns the same action instead of a second one (§3).
 */
export function useAppRequest() {
  const { api } = useSignedIn();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  const pendingKeys = useRef(new Map<string, { key: string; expiresAt: string }>());

  async function request(app: CatalogApp) {
    setBusy(app.id);
    setError(undefined);
    const type = app.installed ? 'app.remove' : 'app.install';
    const slot = `${type}:${app.id}`;
    let pending = pendingKeys.current.get(slot);
    if (!pending) {
      pending = { key: uuidv4(), expiresAt: new Date(Date.now() + REQUEST_TTL_MS).toISOString() };
      pendingKeys.current.set(slot, pending);
    }
    try {
      const action = await api.createAction({
        type,
        params: { app_id: app.id },
        idempotency_key: pending.key,
        expires_at: pending.expiresAt,
      });
      pendingKeys.current.delete(slot);
      navigate(`/approvals?highlight=${encodeURIComponent(action.id)}`);
      return; // this screen unmounts; no more state updates here
    } catch (e) {
      // Keep the key only when the outcome is unknown (network error or 5xx).
      const definite = e instanceof ApiError && e.status >= 400 && e.status < 500;
      if (definite || !(e instanceof ApiError)) pendingKeys.current.delete(slot);
      setError(
        e instanceof ApiError && e.code === 'permission_denied'
          ? 'Your account cannot request installs. Ask the owner.'
          : `Request failed${e instanceof Error ? `: ${e.message}` : ''}.`,
      );
    }
    setBusy(undefined);
  }

  return { busy, error, request };
}
