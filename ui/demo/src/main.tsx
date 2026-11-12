// SPDX-License-Identifier: Apache-2.0
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../../src/styles/index.css';
import './demo.css';
import { DemoApp } from './DemoApp';

// ?theme=light|dark forces a theme (used by the screenshot script); otherwise follow the system.
const theme = new URLSearchParams(window.location.search).get('theme');
if (theme === 'light' || theme === 'dark') document.documentElement.setAttribute('data-theme', theme);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DemoApp />
  </StrictMode>,
);
