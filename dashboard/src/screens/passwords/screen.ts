// SPDX-License-Identifier: Apache-2.0
import type { ScreenDef } from '../types';

// Passwords (#679): the built-in Vaultwarden and its Bitwarden-app setup card. Every signed-in person.
const screen: ScreenDef = {
  id: 'passwords',
  path: '/passwords',
  title: 'Passwords',
  icon: 'lock',
  section: 'Your box',
  order: 77,
  hue: ['#8a5cd6', '#4b2a8f'],
  load: () => import('../../pages/Passwords').then((m) => ({ default: m.Passwords })),
};
export default screen;
