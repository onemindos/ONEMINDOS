// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// Served by its own screen: /updates (the screen's `redirects` send /settings/updates there).
const page: SettingsPageDef = { id: 'updates', to: '/updates' };
export default page;
