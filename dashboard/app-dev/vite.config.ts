// SPDX-License-Identifier: Apache-2.0
import { defineConfig, mergeConfig } from 'vite';
import base from '../vite.config';

// app dev starts its own loopback gateway. Preserve all other dashboard settings and proxy options.
const port = Number(process.env.ONEMIND_PORT);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid local gateway port');
const target = `http://127.0.0.1:${port}`;
const proxy = Object.fromEntries(Object.entries(base.server?.proxy ?? {}).map(([prefix, options]) =>
  [prefix, typeof options === 'string' ? target : { ...options, target }]));

export default defineConfig(mergeConfig(base, { server: { proxy } }));
