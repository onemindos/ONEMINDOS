// SPDX-License-Identifier: Apache-2.0
// A cold first run (CI, or after `npm ci`) transforms every module in parallel; findBy*'s 1 s default
// then times out on screens that are only waiting for the demo backend. 5 s (and testTimeout 20 s in
// package.json) keeps a cold CI run deterministic; a warm run finishes each screen test in about 1 s.
import { configure } from '@testing-library/react-native';

configure({ asyncUtilTimeout: 5000 });
