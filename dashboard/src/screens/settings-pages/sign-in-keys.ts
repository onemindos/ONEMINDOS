// SPDX-License-Identifier: Apache-2.0
import type { SettingsPageDef } from '../types';

const page: SettingsPageDef = { id: 'sign-in-keys', load: () => import('../../pages/SignInKeys').then((module) => ({ default: module.SignInKeys })) };
export default page;
