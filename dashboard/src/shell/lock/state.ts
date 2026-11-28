// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react';
import { personStorage } from '../../data/prefs';

export interface LockSummary {
  boxName: string;
  waiting: number;
  /** The display name of the person who locked, for "Welcome back" (never a token or an id). */
  person?: string;
}

const storedLock = 'onemind.locked';
const idlePreference = 'idle-lock-minutes';
export const idleOptions = [0, 5, 15, 60] as const;
export type IdleMinutes = (typeof idleOptions)[number];

export function saveLock(summary: LockSummary | null) {
  try {
    if (summary) window.sessionStorage.setItem(storedLock, JSON.stringify(summary));
    else window.sessionStorage.removeItem(storedLock);
  } catch { /* Storage is optional, even when credentials have been cleared in memory. */ }
}

export function readLock(): LockSummary | null {
  try {
    const value = window.sessionStorage.getItem(storedLock);
    if (!value) return null;
    const { boxName, waiting, person } = JSON.parse(value);
    if (typeof boxName === 'string' && Number.isSafeInteger(waiting) && waiting >= 0) {
      return typeof person === 'string' && person.trim() ? { boxName, waiting, person: person.trim().slice(0, 64) } : { boxName, waiting };
    }
  } catch { /* No usable snapshot. */ }
  return null;
}

export function readIdleLock(person: string | undefined, isOwner: boolean): IdleMinutes {
  try {
    const value = person && personStorage(person)?.getItem(idlePreference);
    const stored = idleOptions.find((minutes) => String(minutes) === value);
    if (stored !== undefined) return stored;
  } catch { /* Fall back to the role default. */ }
  return isOwner ? 15 : 0;
}

export const idleChangeEvent = 'onemind:idle-lock-change';

export function saveIdleLock(person: string, minutes: IdleMinutes) {
  try { personStorage(person)?.setItem(idlePreference, String(minutes)); } catch { return false; }
  window.dispatchEvent(new Event(idleChangeEvent));
  return true;
}

export function useIdleLockPreference(person: string | undefined, isOwner: boolean) {
  const [, setRevision] = useState(0);
  useEffect(() => {
    const update = () => setRevision((value) => value + 1);
    window.addEventListener(idleChangeEvent, update);
    window.addEventListener('storage', update);
    return () => {
      window.removeEventListener(idleChangeEvent, update);
      window.removeEventListener('storage', update);
    };
  }, []);
  return readIdleLock(person, isOwner);
}

export function useIdleLock(minutes: IdleMinutes, lock: () => void) {
  const onLock = useRef(lock);
  onLock.current = lock;
  useEffect(() => {
    if (!minutes) return;
    let timer: number;
    function activity() {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => onLock.current(), minutes * 60_000);
    }
    const events = ['pointerdown', 'pointermove', 'keydown', 'wheel'] as const;
    events.forEach((event) => window.addEventListener(event, activity, { passive: true }));
    activity();
    return () => {
      window.clearTimeout(timer);
      events.forEach((event) => window.removeEventListener(event, activity));
    };
  }, [minutes]);
}
