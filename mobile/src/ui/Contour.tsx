// SPDX-License-Identifier: Apache-2.0
import { StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { useTheme } from './theme';

// Port the Atlas Contour drawing's overlapping, irregular rings to the phone viewport.
const rings = ([[95, 310, 0.7, 1.4], [340, 630, 2.3, 0.9]] as const).flatMap(([cx, cy, a, b]) =>
  Array.from({ length: 14 }, (_, i) => {
    const base = (i + 1) * 34;
    const points = Array.from({ length: 72 }, (_, j) => {
      const t = j * Math.PI / 36;
      const r = base * (1 + 0.12 * Math.sin(3 * t + a) + 0.07 * Math.sin(5 * t + b) + 0.04 * Math.sin(2 * t + a));
      return `${(cx + Math.cos(t) * r * 1.3).toFixed(1)} ${(cy + Math.sin(t) * r).toFixed(1)}`;
    });
    return `M${points.join(' L')}Z`;
  }),
);

export function Contour() {
  const t = useTheme();
  return (
    <View style={[StyleSheet.absoluteFill, { backgroundColor: t.bg }]} pointerEvents="none" importantForAccessibility="no-hide-descendants">
      <Svg width="100%" height="100%" viewBox="0 0 390 844" preserveAspectRatio="xMidYMid slice">
        {rings.map((d, i) => <Path key={d} d={d} fill="none" stroke={i % 7 === 6 ? t.action : t.borderStrong} strokeOpacity={0.45} strokeWidth={0.75} />)}
      </Svg>
    </View>
  );
}
