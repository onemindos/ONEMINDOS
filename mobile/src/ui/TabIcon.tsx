// SPDX-License-Identifier: Apache-2.0
import Svg, { Path } from 'react-native-svg';
import type { TabParams } from '../nav';

const paths: Record<keyof TabParams, string> = {
  Home: 'M3 10 12 3l9 7v9a2 2 0 0 1-2 2h-4v-6H9v6H5a2 2 0 0 1-2-2z',
  Map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2z M9 4v14 M15 6v14',
  Approvals: 'M9 5H5v16h14V5h-4M9 3h6v4H9z M8 13l3 3 5-6',
  Apps: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  Me: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z M4 21v-2a8 6 0 0 1 16 0v2',
};

export function TabIcon({ name, color }: { name: keyof TabParams; color: string }) {
  return (
    <Svg width={22} height={22} viewBox="0 0 24 24" accessible={false}>
      <Path d={paths[name]} stroke={color} strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </Svg>
  );
}
