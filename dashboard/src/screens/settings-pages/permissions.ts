// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'permissions', load: () => import('../../pages/permissions/PermissionsPage').then((module) => ({ default: module.PermissionsPage })) };
export default page;
