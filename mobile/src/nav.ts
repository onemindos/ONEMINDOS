// SPDX-License-Identifier: Apache-2.0
import type { NavigatorScreenParams } from '@react-navigation/native';

export type TabParams = {
  Home: undefined;
  Nodes: undefined;
  Apps: undefined;
  Approvals: undefined;
  Activity: undefined;
};

export type RootParams = {
  Tabs: NavigatorScreenParams<TabParams> | undefined;
  AppDetail: { id: string };
  Settings: undefined;
};

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface RootParamList extends RootParams {}
  }
}
