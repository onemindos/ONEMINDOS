// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'standing-approvals', load: () => import('../../pages/StandingApprovals').then((module) => ({ default: module.StandingApprovals })) };
export default page;
