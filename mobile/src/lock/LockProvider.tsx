// SPDX-License-Identifier: Apache-2.0
// Lock OneMind (issue #704): with the lock on, the app opens behind an unlock prompt and locks
// again after RELOCK_MS in the background. The lock covers the screen only. It does not put the
// sign-in behind requireAuthentication in the secure store, so background photo backup and push,
// which run without a screen, keep their access while the app is locked.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AppState, Platform, StyleSheet, Text, View } from 'react-native';
import {
  allowScreenCaptureAsync,
  disableAppSwitcherProtectionAsync,
  enableAppSwitcherProtectionAsync,
  preventScreenCaptureAsync,
} from 'expo-screen-capture';
import { readSecret, saveSecret } from '../storage';
import { Button } from '../ui/bits';
import { font, space, useTheme } from '../ui/theme';
import { authenticate, lockAvailable } from './auth';

/** How long the app may sit in the background before it locks again. */
export const RELOCK_MS = 30_000;
export const LOCK_KEY = 'onemind.lock.v1';

export interface Lock {
  /** The phone has a screen lock or biometrics; undefined while checking. */
  available: boolean | undefined;
  enabled: boolean;
  locked: boolean;
  /** Turning the lock on or off needs an unlock first. Resolves true when it changed. */
  setEnabled(on: boolean): Promise<boolean>;
  /** Ask for an unlock for a specific reason (a lock-screen Deny). A success also unlocks the app. */
  confirm(reason: string, requestId: string): Promise<boolean>;
}

const Ctx = createContext<Lock | undefined>(undefined);

export function useLock(): Lock {
  const v = useContext(Ctx);
  if (!v) throw new Error('useLock outside LockProvider');
  return v;
}

/** True while the lock screen covers the app. False outside a LockProvider (the lock is off there). */
export function useIsLocked(): boolean {
  return useContext(Ctx)?.locked ?? false;
}

export function LockProvider({ children, relockMs = RELOCK_MS, now = Date.now }: { children: ReactNode; relockMs?: number; now?: () => number }) {
  const [ready, setReady] = useState(false);
  const [readFailed, setReadFailed] = useState(false);
  const [readAttempt, setReadAttempt] = useState(0);
  const [available, setAvailable] = useState<boolean>();
  const [enabled, setEnabledState] = useState(false);
  const [locked, setLocked] = useState(false);
  const [away, setAway] = useState(AppState.currentState === 'background' || AppState.currentState === 'inactive');
  const [prompt, setPrompt] = useState(0);
  const enabledRef = useRef(false);
  const hiddenAt = useRef<number | undefined>(undefined);

  useEffect(() => {
    let live = true;
    void Promise.all([readSecret(LOCK_KEY), lockAvailable()]).then(([pref, can]) => {
      if (!live) return;
      const on = pref === 'on';
      enabledRef.current = on;
      setAvailable(can);
      setEnabledState(on);
      setLocked(on); // a cold start with the lock on opens locked
      setReady(true);
    }).catch(() => {
      if (live) setReadFailed(true);
    });
    return () => {
      live = false;
    };
  }, [readAttempt]);

  useEffect(() => {
    // Only 'background' counts: the unlock prompt itself makes iOS report 'inactive'.
    const sub = AppState.addEventListener('change', (state) => {
      setAway(state === 'inactive' || state === 'background');
      if (state === 'background') hiddenAt.current ??= now();
      else if (state === 'active') {
        const at = hiddenAt.current;
        hiddenAt.current = undefined;
        if (enabledRef.current && at !== undefined && now() - at >= relockMs) {
          setLocked(true);
          setPrompt((p) => p + 1);
        }
      }
    });
    return () => sub.remove();
  }, [now, relockMs]);

  // The OS can snapshot the native window before JavaScript receives an AppState event.
  // Use native protection in addition to dismissing any separate share modal while away.
  useEffect(() => {
    if (!enabled) return;
    if (Platform.OS === 'ios') {
      void enableAppSwitcherProtectionAsync(1).catch(() => undefined);
      return () => { void disableAppSwitcherProtectionAsync().catch(() => undefined); };
    }
    if (Platform.OS === 'android') {
      void preventScreenCaptureAsync(LOCK_KEY).catch(() => undefined);
      return () => { void allowScreenCaptureAsync(LOCK_KEY).catch(() => undefined); };
    }
  }, [enabled]);

  const unlock = useCallback(async () => {
    const ok = await authenticate('Unlock OneMind');
    if (ok) setLocked(false);
    return ok;
  }, []);

  // Prompt as soon as the app shows locked (start or resume); the button asks again after a cancel.
  useEffect(() => {
    if (ready && locked && available) void unlock();
  }, [ready, locked, available, prompt, unlock]);

  const retry = () => {
    if (readFailed) {
      setReadFailed(false);
      setReadAttempt((attempt) => attempt + 1);
    } else {
      void lockAvailable().then(setAvailable);
    }
  };

  const confirm = useCallback(async (reason: string, requestId: string) => {
    const details = `Request ${requestId}`;
    const ok = Platform.OS === 'android'
      ? await authenticate(reason, Symbol(), details)
      : await authenticate(`${reason}\n${details}`, Symbol());
    if (ok) setLocked(false);
    return ok;
  }, []);

  const setEnabled = useCallback(
    async (on: boolean) => {
      if (on && !available) return false;
      if (!(await authenticate(on ? 'Unlock to turn on Lock OneMind' : 'Unlock to turn off Lock OneMind'))) return false;
      await saveSecret(LOCK_KEY, on ? 'on' : 'off');
      enabledRef.current = on;
      setEnabledState(on);
      setLocked(false);
      return true;
    },
    [available],
  );

  const covered = !ready || locked || (enabled && away);
  const value = useMemo<Lock>(
    () => ({ available, enabled, locked: covered, setEnabled, confirm }),
    [available, enabled, covered, setEnabled, confirm],
  );
  const recovery = readFailed
    ? 'Could not read the Lock OneMind setting.'
    : ready && available === false
      ? 'Phone unlock is unavailable. Check your screen lock in phone settings and try again.'
      : undefined;
  return (
    <Ctx.Provider value={value}>
      {/* Hidden from TalkBack and VoiceOver while the lock covers the screen, so they cannot read or act on what is behind it. */}
      <View
        testID="app-content"
        style={{ flex: 1 }}
        importantForAccessibility={covered ? 'no-hide-descendants' : 'auto'}
        accessibilityElementsHidden={covered}
      >
        {children}
      </View>
      {covered && <LockScreen checking={away || (!ready && !readFailed)} recovery={recovery} onUnlock={() => void unlock()} onRetry={retry} />}
    </Ctx.Provider>
  );
}

function LockScreen({ checking, recovery, onUnlock, onRetry }: { checking: boolean; recovery?: string; onUnlock: () => void; onRetry: () => void }) {
  const t = useTheme();
  return (
    <View testID={checking ? 'app-lock-checking' : 'app-lock'} accessibilityViewIsModal style={[StyleSheet.absoluteFill, { backgroundColor: t.bg, alignItems: 'center', justifyContent: 'center', gap: space.lg, padding: space.xl }]}>
      {!checking && (
        <>
          <Text style={{ color: t.text, fontSize: font.lg, fontWeight: font.bold }}>OneMind is locked</Text>
          <Text style={{ color: t.muted, textAlign: 'center' }}>{recovery ?? 'Unlock with your face, fingerprint or phone PIN.'}</Text>
          {recovery
            ? <Button label="Retry" onPress={onRetry} />
            : <Button testID="unlock" label="Unlock" onPress={onUnlock} />}
        </>
      )}
    </View>
  );
}
