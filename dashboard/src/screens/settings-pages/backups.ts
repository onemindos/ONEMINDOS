// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

// Served by its own screen: /backups (the screen's `redirects` send /settings/backups there).
const page: SettingsPageDef = { id: 'backups', to: '/backups' };
export default page;
