import { Navigate, Route, Routes } from 'react-router';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Layout } from './components/Layout';
import { AppDetail } from './pages/AppDetail';
import { Approvals } from './pages/Approvals';
import { Home } from './pages/Home';
import { Market } from './pages/Market';
import { Nodes } from './pages/Nodes';
import { SignIn } from './pages/SignIn';
import { useSession } from './session';

export function App({ mock }: { mock: boolean }) {
  const { session } = useSession();
  if (!session)
    return (
      <ErrorBoundary>
        <SignIn mock={mock} />
      </ErrorBoundary>
    );
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="nodes" element={<Nodes />} />
          <Route path="market" element={<Market />} />
          <Route path="market/:appId" element={<AppDetail />} />
          <Route path="approvals" element={<Approvals />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}
