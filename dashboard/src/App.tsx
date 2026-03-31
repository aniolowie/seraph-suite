import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { LoadingSpinner } from './components/shared/LoadingSpinner';

const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const BenchmarksPage = lazy(() => import('./pages/BenchmarksPage').then((m) => ({ default: m.BenchmarksPage })));
const BenchmarkDetailPage = lazy(() => import('./pages/BenchmarkDetailPage').then((m) => ({ default: m.BenchmarkDetailPage })));
const KnowledgePage = lazy(() => import('./pages/KnowledgePage').then((m) => ({ default: m.KnowledgePage })));
const LearningPage = lazy(() => import('./pages/LearningPage').then((m) => ({ default: m.LearningPage })));
const MachinesPage = lazy(() => import('./pages/MachinesPage').then((m) => ({ default: m.MachinesPage })));
const WriteupSubmitPage = lazy(() => import('./pages/WriteupSubmitPage').then((m) => ({ default: m.WriteupSubmitPage })));

export function App() {
  return (
    <Layout>
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/benchmarks" element={<BenchmarksPage />} />
          <Route path="/benchmarks/:runId" element={<BenchmarkDetailPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/learning" element={<LearningPage />} />
          <Route path="/machines" element={<MachinesPage />} />
          <Route path="/writeups/submit" element={<WriteupSubmitPage />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
