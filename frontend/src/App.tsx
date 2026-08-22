import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './layouts/MainLayout';
import { AuthProvider } from './auth/AuthContext';
import RequireAuth from './auth/RequireAuth';
import LoginPage from './pages/auth/LoginPage';
import DataSourceList from './pages/datasource/DataSourceList';
import DataSourceDetail from './pages/datasource/DataSourceDetail';
import OntologyList from './pages/ontology/OntologyList';
import OntologyDetailPage from './pages/ontology/OntologyDetail';
import MappingList from './pages/mapping/MappingList';
import RuleList from './pages/rules/RuleList';
import SemanticService from './pages/semantic';
import Governance from './pages/governance';
import DemoCenter from './pages/demo/DemoCenter';
import ModelConfigPage from './pages/model/ModelConfig';
import OntologyChat from './pages/chat/OntologyChat';
import WorkbenchPage from './pages/workbench';
import OntologyGraphPage from './pages/graph/OntologyGraph';
import KnowledgeBasePage from './pages/knowledge/KnowledgeBase';
import WorkflowManager from './pages/workflow/WorkflowManager';
import PermissionManager from './pages/permission/PermissionManager';

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
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
              <Route path="workbench" element={<WorkbenchPage />} />
              <Route path="graph" element={<OntologyGraphPage />} />
              <Route path="knowledge" element={<KnowledgeBasePage />} />
              <Route path="chat" element={<OntologyChat />} />
              <Route path="datasource" element={<DataSourceList />} />
              <Route path="datasource/:id" element={<DataSourceDetail />} />
              <Route path="ontology" element={<OntologyList />} />
              <Route path="ontology/:id" element={<OntologyDetailPage />} />
              <Route path="mapping" element={<MappingList />} />
              <Route path="rules" element={<RuleList />} />
              <Route path="semantic" element={<SemanticService />} />
              <Route path="governance" element={<Governance />} />
              <Route path="demo" element={<DemoCenter />} />
              <Route path="model" element={<ModelConfigPage />} />
              <Route path="workflow" element={<WorkflowManager />} />
              <Route path="permission" element={<PermissionManager />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;
