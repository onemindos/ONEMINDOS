// SPDX-License-Identifier: Apache-2.0
import type { NavigatorScreenParams } from '@react-navigation/native';

/** Phone navigation per docs/design/IA.md §1 and §3: four primary tabs plus More. */
export type TabParams = {
  Home: undefined;
  Apps: undefined;
  Approvals: undefined;
  Activity: undefined;
  More: undefined;
};

export type RootParams = {
  Tabs: NavigatorScreenParams<TabParams> | undefined;
  AppDetail: { id: string };
  Settings: undefined;
  PhotoBackup: undefined;
  PhotoAlbums: undefined;
  /** Under More (IA §3); pushes open it directly. */
  Inbox: { id?: string } | undefined;
  Nodes: undefined;
  Backups: undefined;
  Automation: undefined;
  Files: undefined;
  Migrate: undefined;
};

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface RootParamList extends RootParams {}
  }
}
