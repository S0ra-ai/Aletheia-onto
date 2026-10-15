import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './layouts/MainLayout';
import NotFound from './pages/NotFound';
import { AuthProvider } from './auth/AuthContext';
import RequireAuth from './auth/RequireAuth';
import LoginPage from './pages/auth/LoginPage';
import ErrorBoundary from './error-boundary/ErrorBoundary';

// Lazy load pages for better performance
const WorkbenchPage = lazy(() => import('./pages/workbench'));
const OntologyGraphPage = lazy(() => import('./pages/graph/OntologyGraph'));
const KnowledgeBasePage = lazy(() => import('./pages/knowledge/KnowledgeBase'));
const FeedbackConsolePage = lazy(() => import('./pages/feedback/FeedbackConsole'));
const OntologyChat = lazy(() => import('./pages/chat/OntologyChat'));
const DataSourceList = lazy(() => import('./pages/datasource/DataSourceList'));
const DataSourceDetail = lazy(() => import('./pages/datasource/DataSourceDetail'));
const OntologyList = lazy(() => import('./pages/ontology/OntologyList'));
const OntologyDetailPage = lazy(() => import('./pages/ontology/OntologyDetail'));
const MappingList = lazy(() => import('./pages/mapping/MappingList'));
const RuleList = lazy(() => import('./pages/rules/RuleList'));
const SemanticService = lazy(() => import('./pages/semantic'));
const ObjectBrowser = lazy(() => import('./pages/objects/ObjectBrowser'));
const Governance = lazy(() => import('./pages/governance'));
const DemoCenter = lazy(() => import('./pages/demo/DemoCenter'));
const ModelConfigPage = lazy(() => import('./pages/model/ModelConfig'));
const WorkflowManager = lazy(() => import('./pages/workflow/WorkflowManager'));
const PermissionManager = lazy(() => import('./pages/permission/PermissionManager'));
const BackupManager = lazy(() => import('./pages/backup/BackupManager'));

// Loading fallback component
const PageLoader = () => (
  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '400px' }}>
    <Spin size="large" tip="加载中..." />
  </div>
);

// Vite serves the app at `/` during development; the production image mounts it at
// `/admin` beside the API. Keeping the base conditional avoids making the dev server
// appear blank while still allowing a single-origin production deployment.
const ROUTER_BASENAME = import.meta.env.PROD ? '/admin' : '/';

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter basename={ROUTER_BASENAME}>
        <ErrorBoundary>
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/"
                element={
                  <RequireAuth>
                    <MainLayout />
                  </RequireAuth>
                }
              >
                <Route index element={<Navigate to="/workbench" replace />} />
                <Route
                  path="workbench"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <WorkbenchPage />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="graph"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <OntologyGraphPage />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="knowledge"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <KnowledgeBasePage />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="feedback"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <FeedbackConsolePage />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="chat"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <OntologyChat />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="datasource"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <DataSourceList />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="datasource/:id"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <DataSourceDetail />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="ontology"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <OntologyList />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="ontology/:id"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <OntologyDetailPage />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="mapping"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <MappingList />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="rules"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <RuleList />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="semantic"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <SemanticService />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="governance"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <Governance />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="demo"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <DemoCenter />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="model"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <ModelConfigPage />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="workflow"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <WorkflowManager />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="permission"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <PermissionManager />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="data-backup"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <BackupManager />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route
                  path="objects"
                  element={
                    <ErrorBoundary fullPage>
                      <Suspense fallback={<PageLoader />}>
                        <ObjectBrowser />
                      </Suspense>
                    </ErrorBoundary>
                  }
                />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Routes>
          </AuthProvider>
        </ErrorBoundary>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;
