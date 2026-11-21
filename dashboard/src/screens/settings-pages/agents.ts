// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'agents', load: () => import('../../pages/Tokens').then((m) => ({ default: m.Tokens })) };
export default page;
