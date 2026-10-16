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
import type { MessageKey } from '../i18n/messages';

const ROLE_KEYS: Record<string, MessageKey> = {
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
interface MenuItem {
  key: string;
  icon: React.ReactNode;
  labelKey: MessageKey;
  children?: MenuItem[];
}

const menuItems: MenuItem[] = [
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
  // Inferred rather than annotated: antd's `ItemType` is a union whose `children` is required
  // on one arm and absent on the other, and naming the shape explicitly makes the two arms
  // collapse into one optional property that no longer matches either. `labelKey` is
  // deliberately not carried through -- the dictionary key is the source's business, and a
  // spread would leave a second, unchecked place for the rendered label to come from.
  const items = menuItems.map((item) => {
    const label = t(item.labelKey);
    const children = item.children ?? [];
    if (!children.length) return { key: item.key, icon: item.icon, label };
    return {
      key: item.key,
      icon: item.icon,
      label,
      children: children.map((child) => ({ key: child.key, icon: child.icon, label: t(child.labelKey) })),
    };
  });
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  // The route's first segment, which is what every menu key is written against. Computed
  // once because both the selection and the open group are derived from it, and two copies
  // of `path.split('/')[1]` are two chances to disagree about what page this is.
  const firstSegment = location.pathname === '/' ? '/workbench' : '/' + location.pathname.split('/')[1];

  const getSelectedKey = () => {
    const navigableItems = items.flatMap(item => ('children' in item ? item.children : [item]));
    return navigableItems.find(item => item?.key === firstSegment)?.key || '/';
  };

  // Which submenu contains the current route, so the group is open when a page inside it is
  // open. Derived from the menu rather than listed by hand.
  //
  // It was a hand-written chain of `startsWith` calls, and it had already drifted: `/tenancy`
  // is a child of 更多 but was missing from the chain, so arriving at Tenancy -- by link, by
  // bookmark, by refresh -- left the group collapsed and the selected item invisible. The
  // next child added would have done the same, silently, because nothing tied the two lists
  // together. Reading the same `children` array that renders the menu cannot drift.
  const openKeys = items
    .filter(item => 'children' in item && (item.children ?? []).some(child => child.key === firstSegment))
    .map(item => item.key);

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
          textOverflow: 'ellipsis',
        }}>
          {/* `shell.app.name` was in the dictionary the whole time while this line kept its
              own copy of the Chinese -- the one string on every screen that had a translation
              and never used it. The collapsed form is short in either script, so it is a
              message too: 「本体」 is one glyph and 'Aletheia' is the product's name.

              Expanded, the wordmark is its own message rather than the page title: the sider
              is 200px wide and the English title does not fit, so it rendered as
              「Aletheia Ontology P」 -- cut mid-word, with no ellipsis, on every English screen.
              `textOverflow` is the backstop: a name that does not fit should trail off with …, 
              which tells the reader it is truncated, rather than stop mid-word, which looks
              like a typo in the product's own name. */}
          {collapsed ? t('shell.app.nameShort') : t('shell.app.siderName')}
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
            <Tag color="blue">{user?.roleCode ? t(ROLE_KEYS[user.roleCode] ?? 'shell.role.operator') : ''}</Tag>
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
