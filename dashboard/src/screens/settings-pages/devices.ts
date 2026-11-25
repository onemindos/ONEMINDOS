// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// Served by its own screen: /nodes (the screen's `redirects` send /settings/devices there).
const page: SettingsPageDef = { id: 'devices', to: '/nodes' };
export default page;
