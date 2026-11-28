// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'notifications', load: () => import('../../pages/Inbox').then((m) => ({ default: m.NotificationSettings })) };
export default page;
