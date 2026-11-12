// SPDX-License-Identifier: Apache-2.0
// Minimal tokens. A later design pass restyles the app; screens use only these.
import { useColorScheme } from 'react-native';

const light = {
  bg: '#F6F7F9',
  card: '#FFFFFF',
  text: '#14171C',
  muted: '#5C6470',
  border: '#E3E6EA',
  accent: '#2F5BEA',
  accentText: '#FFFFFF',
  ok: '#1E7F4F',
  okBg: '#E3F4EA',
  warn: '#8A5A00',
  warnBg: '#FFF2D6',
  bad: '#B42318',
  badBg: '#FDE7E5',
  info: '#2F5BEA',
  infoBg: '#E6ECFD',
  neutralBg: '#EEF0F3',
};
export type Palette = typeof light;

const dark: Palette = {
  bg: '#0F1115',
  card: '#181B21',
  text: '#ECEEF1',
  muted: '#9AA3AF',
  border: '#2A2F37',
  accent: '#7C9BFF',
  accentText: '#0F1115',
  ok: '#5FD394',
  okBg: '#14301F',
  warn: '#F2C14E',
  warnBg: '#3A2E10',
  bad: '#FF7B70',
  badBg: '#3D1714',
  info: '#7C9BFF',
  infoBg: '#1A2442',
  neutralBg: '#22262D',
};

export function useTheme(): Palette {
  return useColorScheme() === 'dark' ? dark : light;
}

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const radius = 12;
