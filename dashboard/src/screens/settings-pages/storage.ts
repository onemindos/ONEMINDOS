// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// Served by its own screen: /storage (the screen's `redirects` send /settings/storage there).
const page: SettingsPageDef = { id: 'storage', to: '/storage' };
export default page;
