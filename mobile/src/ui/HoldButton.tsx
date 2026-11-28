// SPDX-License-Identifier: Apache-2.0
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { NavigationContext } from '@react-navigation/native';
import { AccessibilityInfo, Animated, AppState, Pressable, StyleSheet, Text } from 'react-native';
import type { Action } from '../api/types';
import { s } from './bits';
import { font, useTheme } from './theme';

const HOLD_MS = 2000;

export function requiresHold(a: Pick<Action, 'risk' | 'approval'>): boolean {
  return a.risk === 'actuate' || a.risk === 'destructive' || (typeof a.approval === 'object' && a.approval?.physical === true);
}

export function HoldButton({ label, onComplete, disabled, testID }: {
  label: string;
  onComplete: (holdMs: number) => void;
  disabled: boolean;
  testID: string;
}) {
  const t = useTheme();
  const nav = useContext(NavigationContext);
  const start = useRef<number | null>(null);
  const [holding, setHolding] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(true);
  const [progress] = useState(() => new Animated.Value(0));

  const cancel = useCallback(() => {
    start.current = null;
    progress.stopAnimation();
    progress.setValue(0);
    setHolding(false);
  }, [progress]);

  useEffect(() => {
    let mounted = true;
    let receivedChange = false;
    const motion = AccessibilityInfo.addEventListener('reduceMotionChanged', (value) => {
      receivedChange = true;
      setReduceMotion(value);
    });
    void AccessibilityInfo.isReduceMotionEnabled().then((value) => {
      if (mounted && !receivedChange) setReduceMotion(value);
    }).catch(() => undefined);
    const app = AppState.addEventListener('change', (state) => { if (state !== 'active') cancel(); });
    const blur = nav?.addListener('blur', cancel);
    return () => {
      mounted = false;
      start.current = null;
      progress.stopAnimation();
      motion.remove();
      app.remove();
      blur?.();
    };
  }, [cancel, nav, progress]);

  useEffect(() => {
    if (disabled) cancel();
  }, [cancel, disabled]);

  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint="Hold for two seconds, then sign the approval. With a screen reader, double-tap and hold."
      accessibilityState={{ disabled }}
      disabled={disabled}
      delayLongPress={HOLD_MS}
      onPressIn={(event) => {
        if (disabled || event.nativeEvent.touches.length !== 1) return;
        start.current = performance.now();
        setHolding(true);
        if (!reduceMotion) Animated.timing(progress, { toValue: 1, duration: HOLD_MS, useNativeDriver: false }).start();
      }}
      onPressOut={cancel}
      onLongPress={() => {
        if (disabled || start.current === null || performance.now() - start.current < HOLD_MS) return;
        cancel();
        onComplete(HOLD_MS);
      }}
      style={[s.btn, { minHeight: 48, backgroundColor: t.action, borderColor: t.action, opacity: disabled ? 0.55 : 1, overflow: 'hidden' }]}
    >
      {!reduceMotion && <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, {
        width: progress.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }),
        backgroundColor: t.actionHover,
      }]} />}
      <Text style={{ color: t.actionText, fontSize: font.sm, fontWeight: font.bold }}>{label}</Text>
      {holding && <Text style={{ color: t.actionText, fontSize: font.xs }}>Keep holding for 2 seconds</Text>}
    </Pressable>
  );
}
