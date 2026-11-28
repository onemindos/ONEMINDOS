// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// Served by its own screen: /network (the screen's `redirects` send /settings/network there).
const page: SettingsPageDef = { id: 'network', to: '/network' };
export default page;
