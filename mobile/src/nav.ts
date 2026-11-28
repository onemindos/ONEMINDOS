// SPDX-License-Identifier: Apache-2.0
import type { NavigatorScreenParams } from '@react-navigation/native';

/** Atlas phone tabs. The Map tab lands separately (#656). */
export type TabParams = {
  Home: undefined;
  Approvals: { id?: string; reviewKey?: number } | undefined;
  Apps: undefined;
  Me: undefined;
};

export type RootParams = {
  Tabs: NavigatorScreenParams<TabParams> | undefined;
  Activity: undefined;
  AppDetail: { id: string };
  Tips: { id?: string } | undefined;
  Settings: undefined;
  Permissions: undefined;
  PhotoBackup: undefined;
  PhotoAlbums: undefined;
  /** Under More (IA §3); pushes open it directly. */
  Inbox: { id?: string } | undefined;
  Nodes: undefined;
  Backups: undefined;
  Automation: undefined;
  Files: undefined;
  Migrate: undefined;
  People: undefined;
  Agents: undefined;
  OsUpdates: undefined;
  SystemControls: undefined;
  DeviceInfo: undefined;
  LiveUsage: undefined;
  Network: undefined;
};

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface RootParamList extends RootParams {}
  }
}
