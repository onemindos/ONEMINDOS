// SPDX-License-Identifier: Apache-2.0
// /apps/<id>/<route>: the web path of the onemind://app/<id>/<route> deep link (#617, lib/appLinks.ts).
// A built-in app the dashboard draws itself opens its own screen; every other app opens its app page.
import { Navigate, useParams } from 'react-router';
import { builtInScreenPath } from '../lib/appLinks';
import { SCREENS } from '../screens/registry';
import { AppPage } from './AppPage';

const SCREEN_PATHS: ReadonlyMap<string, string> = new Map(SCREENS.filter((s) => !s.path.includes(':')).map((s) => [s.id, s.path]));

export function AppRoute() {
  const { appId = '', '*': route = '' } = useParams();
  const screen = builtInScreenPath(appId, route, SCREEN_PATHS);
  return screen ? <Navigate to={screen} replace /> : <AppPage />;
}
