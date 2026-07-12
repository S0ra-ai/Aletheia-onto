import React, { useState } from 'react';
import { Layout, Menu, theme } from 'antd';
import {
  DatabaseOutlined,
  SettingOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';

const { Header, Sider, Content } = Layout;

const menuItems = [
  {
    key: '/chat',
    icon: <MessageOutlined />,
    label: '对话',
  },
  {
    key: '/datasource',
    icon: <DatabaseOutlined />,
    label: '数据源管理',
  },
  {
    key: '/model',
    icon: <SettingOutlined />,
    label: '模型配置',
  },
];

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const getSelectedKey = () => {
    const path = location.pathname;
    if (path === '/') return '/chat';
    const firstSegment = '/' + path.split('/')[1];
    return menuItems.find(item => item.key === firstSegment)?.key || '/';
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="dark"
      >
        <div style={{ 
          height: 32, 
          margin: 16, 
          color: 'white',
          fontSize: collapsed ? 14 : 18,
          fontWeight: 'bold',
          textAlign: 'center',
          lineHeight: '32px',
          overflow: 'hidden',
          whiteSpace: 'nowrap',
        }}>
          {collapsed ? '本体' : '本体改造研发平台'}
        </div>
        <Menu
          theme="dark"
          selectedKeys={[getSelectedKey()]}
          mode="inline"
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ 
          padding: '0 24px', 
          background: colorBgContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 16, fontWeight: 500 }}>
            本体改造研发平台
          </div>
          <div style={{ color: '#666' }}>v0.1.0</div>
        </Header>
        <Content style={{ margin: 24 }}>
          <div style={{
            padding: 24,
            minHeight: 360,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
          }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
