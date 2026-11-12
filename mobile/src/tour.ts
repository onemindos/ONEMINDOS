// SPDX-License-Identifier: Apache-2.0
// Screenshot tour for docs/screenshots. Off unless the JS bundle is built with
// EXPO_PUBLIC_SCREENSHOT_TOUR=owner|adult|agent (Expo inlines EXPO_PUBLIC_* at
// bundle time). It opens the demo (mock data only, never a real hub) and steps
// through the screens every TOUR_STEP_MS, so a script can take screenshots
// without tapping. Normal builds never set the variable.
const role = process.env.EXPO_PUBLIC_SCREENSHOT_TOUR;

export const TOUR_ROLE: 'owner' | 'adult' | 'agent' | undefined =
  role === 'owner' || role === 'adult' || role === 'agent' ? role : undefined;

export const TOUR_STEP_MS = 8000;

export type TourStep =
  | { tab: 'Home' | 'Nodes' | 'Apps' | 'Approvals' | 'Activity' }
  | { app: string }
  | { settings: true }
  | { photos: 'screen' | 'enable' | 'albums' | 'cellular' | 'wifi' };

export const TOUR: TourStep[] = [
  { tab: 'Home' },
  { tab: 'Nodes' },
  { tab: 'Apps' },
  { app: 'ollama' },
  { app: 'node-red' },
  { tab: 'Approvals' },
  { tab: 'Activity' },
  { settings: true },
  { photos: 'screen' },
  { photos: 'enable' },
  { photos: 'albums' },
  { photos: 'cellular' },
  { photos: 'wifi' },
  { photos: 'screen' },
  { photos: 'screen' },
  { photos: 'screen' },
  { tab: 'Home' },
];
