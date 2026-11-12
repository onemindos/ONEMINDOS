// SPDX-License-Identifier: Apache-2.0
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './App';
import { MockApi } from './api/mock';
import { SessionProvider, type SessionDeps } from './session';
import './app.css';

const mock = import.meta.env.VITE_MOCK === '1';
// In the demo the noop executor takes 1.5 s per step, so live install progress can be seen.
const deps: SessionDeps = { mock, makeApi: mock ? (t) => new MockApi(t, { stepMs: 1500 }) : undefined };

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider deps={deps}>
        <App mock={mock} />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
