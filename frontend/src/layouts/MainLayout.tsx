import React, { useState } from 'react';
import { Button, Dropdown, Layout, Menu, Space, Tag, theme } from 'antd';
import {
  DatabaseOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  ApartmentOutlined,
  SafetyOutlined,
  LogoutOutlined,
  UserOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  ShareAltOutlined,
  FileProtectOutlined,
  AuditOutlined,
  BookOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';

const ROLE_LABELS: Record<string, string> = {
  admin: '系统管理员',
  ontology_engineer: '本体工程师',
  business_expert: '业务专家',
  operator: '操作员',
  analyst: '分析师',
  ai_agent: 'AI 智能体',
};

const { Header, Sider, Content } = Layout;

// Several routes existed but had no menu entry, so they were only reachable by
// typing a URL. Listed here in the order an operator actually works through:
// see what needs doing, connect a source, model it, govern it, then ask.
const menuItems = [
  {
    key: '/workbench',
    icon: <DashboardOutlined />,
    label: '工作台',
  },
  {
    key: '/datasource',
    icon: <DatabaseOutlined />,
    label: '数据源管理',
  },
  {
    key: '/ontology',
    icon: <DeploymentUnitOutlined />,
    label: '本体管理',
  },
  {
    key: '/graph',
    icon: <ShareAltOutlined />,
    label: '知识图谱',
  },
  {
    key: '/knowledge',
    icon: <BookOutlined />,
    label: '文档知识库',
  },
  {
    key: '/mapping',
    icon: <AuditOutlined />,
    label: '语义映射',
  },
  {
    key: '/rules',
    icon: <FileProtectOutlined />,
    label: '业务规则',
  },
  {
    key: '/governance',
    icon: <SafetyOutlined />,
    label: '治理与留痕',
  },
  {
    key: '/chat',
    icon: <ThunderboltOutlined />,
    label: '智能体对话',
  },
  {
    key: '/workflow',
    icon: <ApartmentOutlined />,
    label: '工作流管理',
  },
  {
    key: '/permission',
    icon: <SafetyOutlined />,
    label: '权限管理',
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
  const { user, signOut } = useAuth();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const getSelectedKey = () => {
    const path = location.pathname;
    if (path === '/') return '/workbench';
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
          <Space size="middle">
            <Tag color="blue">{ROLE_LABELS[user?.roleCode ?? ''] ?? user?.roleCode}</Tag>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: '退出登录',
                    onClick: async () => {
                      await signOut();
                      navigate('/login', { replace: true });
                    },
                  },
                ],
              }}
            >
              <Button type="text" icon={<UserOutlined />}>
                {user?.displayName || user?.username}
              </Button>
            </Dropdown>
          </Space>
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
