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
  ClusterOutlined,
  DashboardOutlined,
  ProfileOutlined,
  DeploymentUnitOutlined,
  ShareAltOutlined,
  FileProtectOutlined,
  AuditOutlined,
  BookOutlined,
  MessageOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/useAuth';
import { useLocale } from '../i18n/locale';

const ROLE_KEYS: Record<string, string> = {
  admin: 'shell.role.admin',
  ontology_engineer: 'shell.role.ontology_engineer',
  business_expert: 'shell.role.business_expert',
  operator: 'shell.role.operator',
  analyst: 'shell.role.analyst',
  ai_agent: 'shell.role.ai_agent',
};

const { Header, Sider, Content } = Layout;

// Keep the first screen focused on the single business path. Advanced tools remain
// reachable under “更多”, so nothing is hidden by role or permission.
const menuItems = [
  {
    key: '/workbench',
    icon: <DashboardOutlined />,
    labelKey: 'shell.nav.workbench',
  },
  {
    key: '/datasource',
    icon: <DatabaseOutlined />,
    labelKey: 'shell.nav.datasource',
  },
  {
    key: '/ontology',
    icon: <DeploymentUnitOutlined />,
    labelKey: 'shell.nav.ontology',
  },
  {
    key: '/governance',
    icon: <SafetyOutlined />,
    labelKey: 'shell.nav.governance',
  },
  {
    key: '/chat',
    icon: <ThunderboltOutlined />,
    labelKey: 'shell.nav.chat',
  },
  {
    key: '/objects',
    icon: <ProfileOutlined />,
    labelKey: 'shell.nav.objects',
  },
  {
    key: '/more',
    icon: <SettingOutlined />,
    labelKey: 'shell.nav.more',
    children: [
      { key: '/graph', icon: <ShareAltOutlined />, labelKey: 'shell.nav.graph' },
      { key: '/knowledge', icon: <BookOutlined />, labelKey: 'shell.nav.knowledge' },
      { key: '/mapping', icon: <AuditOutlined />, labelKey: 'shell.nav.mapping' },
      { key: '/rules', icon: <FileProtectOutlined />, labelKey: 'shell.nav.rules' },
      { key: '/feedback', icon: <MessageOutlined />, labelKey: 'shell.nav.feedback' },
      { key: '/workflow', icon: <ApartmentOutlined />, labelKey: 'shell.nav.workflow' },
      { key: '/permission', icon: <SafetyOutlined />, labelKey: 'shell.nav.permission' },
      // Not `/backup`: `/admin/backup` is an API namespace the access policy keeps out of
      // the SPA shell -- archives hold credentials -- so a page there is served raw 401
      // JSON on a refresh or a bookmark instead of the application.
      { key: '/tenancy', icon: <ClusterOutlined />, labelKey: 'shell.nav.tenancy' },
      { key: '/data-backup', icon: <DatabaseOutlined />, labelKey: 'shell.nav.backup' },
      { key: '/model', icon: <SettingOutlined />, labelKey: 'shell.nav.model' },
    ],
  },
];

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuth();
  const { locale, setLocale, t } = useLocale();

  /**
   * The menu is built here rather than at module scope, because a label is a function of the
   * chosen language -- a module-scope array is translated once, at import, and stays in
   * whichever language the bundle happened to start in.
   */
  const items = menuItems.map((item) => {
    const label = t(item.labelKey as never);
    const children = 'children' in item ? (item.children ?? []) : [];
    if (!children.length) return { key: item.key, icon: item.icon, label };
    return {
      key: item.key,
      icon: item.icon,
      label,
      children: children.map((child) => ({ ...child, label: t(child.labelKey as never) })),
    };
  });
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const getSelectedKey = () => {
    const path = location.pathname;
    if (path === '/') return '/workbench';
    const firstSegment = '/' + path.split('/')[1];
    const navigableItems = items.flatMap(item => 'children' in item ? item.children : [item]);
    return navigableItems.find(item => item?.key === firstSegment)?.key || '/';
  };

  const openKeys = location.pathname.startsWith('/graph') || location.pathname.startsWith('/knowledge')
    || location.pathname.startsWith('/mapping') || location.pathname.startsWith('/rules')
    || location.pathname.startsWith('/feedback') || location.pathname.startsWith('/workflow')
    || location.pathname.startsWith('/permission') || location.pathname.startsWith('/data-backup')
    || location.pathname.startsWith('/model') ? ['/more'] : [];

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
          defaultOpenKeys={openKeys}
          mode="inline"
          items={items}
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
            {t('shell.app.name')}
          </div>
          <Space size="middle">
            <Tag color="blue">{user?.roleCode ? t((ROLE_KEYS[user.roleCode] ?? 'shell.role.operator') as never) : ''}</Tag>
            {/* The switch sits in the header, next to the account: it is a property of the
                person reading, not of a page. Both languages are written in their own script
                (`中文` / `English`) so the choice is legible before it is made. */}
            <Dropdown
              menu={{
                selectable: true,
                selectedKeys: [locale],
                items: [
                  { key: 'zh', label: t('shell.account.chinese'), onClick: () => setLocale('zh') },
                  { key: 'en', label: t('shell.account.english'), onClick: () => setLocale('en') },
                ],
              }}
            >
              <Button type="text" icon={<GlobalOutlined />} aria-label={t('shell.account.language')}>
                {locale === 'zh' ? '中文' : 'English'}
              </Button>
            </Dropdown>
            <Dropdown
              menu={{
                items: [
                  {
                    key: 'logout',
                    icon: <LogoutOutlined />,
                    label: t('shell.account.logout'),
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
