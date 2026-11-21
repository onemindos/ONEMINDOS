// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'agents', load: () => import('../../pages/AgentsSettings').then((m) => ({ default: m.AgentsSettings })) };
export default page;
