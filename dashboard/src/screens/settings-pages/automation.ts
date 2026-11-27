// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// Served by its own screen: /automation (the screen's `redirects` send /settings/automation there).
const page: SettingsPageDef = { id: 'automation', to: '/automation' };
export default page;
