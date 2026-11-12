import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import { App } from './App';
import { SessionProvider, type SessionDeps } from './session';
import './styles.css';

const mock = import.meta.env.VITE_MOCK === '1';
const deps: SessionDeps = { mock };

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <SessionProvider deps={deps}>
        <App mock={mock} />
      </SessionProvider>
    </BrowserRouter>
  </StrictMode>,
);
