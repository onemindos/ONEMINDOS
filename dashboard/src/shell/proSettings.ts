// SPDX-License-Identifier: Apache-2.0
import type { SettingsSectionId } from '@onemind/ui';

/** Settings sections for the people who run the box (UX-01, #206): hidden from the list for Simple roles and
 * unknown roles, and a direct link shows the role notice. Appearance, Account, Notifications and About stay for everyone.
 * Kept out of pages/Settings so the window manager does not pull the lazy Settings screen into the main bundle. */
export const PRO_SETTINGS: ReadonlySet<SettingsSectionId> = new Set<SettingsSectionId>(['users', 'agents', 'devices', 'network', 'storage', 'backups', 'updates', 'automation', 'care']);
