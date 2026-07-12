import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './layouts/MainLayout';
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

const App: React.FC = () => {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/chat" replace />} />
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
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default App;
