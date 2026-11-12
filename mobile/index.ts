// SPDX-License-Identifier: Apache-2.0
import { registerRootComponent } from 'expo';

import App from './App';
// Defines the photo backup task before the OS can start the app in the background.
import './src/photos/background';

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
// It also ensures that whether you load the app in Expo Go or in a native build,
// the environment is set up appropriately
registerRootComponent(App);
