/**
 * The shell: navigation, header, loading, and the language switch itself.
 *
 * Each screen adds its own file next to this one and exports the same shape. `MESSAGES` in
 * `./index.ts` merges them, and a test asserts that every key exists in both languages and
 * that the placeholder names match -- a translation is a claim about the other language, and
 * the only part of it a machine can check is the shape.
 */

export interface MessageEntry {
  zh: string;
  en: string;
}

export const shell = {
  'app.name': { zh: '本体改造研发平台', en: 'Ontology Platform' },
  'app.loading': { zh: '加载中…', en: 'Loading…' },

  'nav.workbench': { zh: '工作台', en: 'Workbench' },
  'nav.datasource': { zh: '数据接入', en: 'Data sources' },
  'nav.ontology': { zh: '知识建模', en: 'Modelling' },
  'nav.governance': { zh: '治理与留痕', en: 'Governance' },
  'nav.chat': { zh: '业务研判', en: 'Ask the model' },
  'nav.more': { zh: '更多工具', en: 'More tools' },
  'nav.objects': { zh: '对象浏览', en: 'Business objects' },
  'nav.graph': { zh: '本体图谱', en: 'Ontology graph' },
  'nav.knowledge': { zh: '文档知识库', en: 'Knowledge base' },
  'nav.mapping': { zh: '语义映射', en: 'Semantic mappings' },
  'nav.rules': { zh: '业务规则', en: 'Business rules' },
  'nav.feedback': { zh: '反馈闭环', en: 'Feedback' },
  'nav.workflow': { zh: '工作流管理', en: 'Workflows' },
  'nav.permission': { zh: '权限管理', en: 'Permissions' },
  'nav.tenancy': { zh: '租户管理', en: 'Tenants' },
  'nav.backup': { zh: '数据备份', en: 'Backups' },
  'nav.model': { zh: '模型配置', en: 'Model configuration' },
  'nav.demo': { zh: '演示中心', en: 'Demo' },

  'role.admin': { zh: '系统管理员', en: 'Administrator' },
  'role.ontology_engineer': { zh: '本体工程师', en: 'Ontology engineer' },
  'role.business_expert': { zh: '业务专家', en: 'Business expert' },
  'role.operator': { zh: '操作员', en: 'Operator' },
  'role.analyst': { zh: '分析师', en: 'Analyst' },
  'role.ai_agent': { zh: 'AI 智能体', en: 'AI agent' },

  'account.logout': { zh: '退出登录', en: 'Sign out' },
  'account.language': { zh: '语言', en: 'Language' },
  'account.chinese': { zh: '中文', en: '中文' },
  'account.english': { zh: 'English', en: 'English' },

  'login.title': { zh: '本体改造研发平台', en: 'Ontology Platform' },
  'login.subtitle': { zh: '请使用平台账号登录。', en: 'Sign in with a platform account.' },
  'login.username': { zh: '用户名', en: 'Username' },
  'login.password': { zh: '密码', en: 'Password' },
  'login.usernameRequired': { zh: '请输入用户名', en: 'Enter a username' },
  'login.passwordRequired': { zh: '请输入密码', en: 'Enter a password' },
  'login.submit': { zh: '登录', en: 'Sign in' },
  'login.failed': { zh: '登录失败，请重试。', en: 'Sign-in failed. Try again.' },
  'login.firstRun': {
    zh: '首次使用：管理员账号是 admin，口令在 aletheia init 的输出里，只显示一次。忘记了就在服务器上运行 aletheia passwd 重设（会提示输入新口令）。',
    en: 'First run: the administrator account is admin, and its password is printed once by aletheia init. If it is lost, run aletheia passwd on the server to set a new one (it prompts, so the password stays out of your shell history).',
  },

  'notFound.title': { zh: '页面不存在', en: 'Page not found' },
  'notFound.subtitle': {
    zh: '这个地址没有对应的页面。可能是链接已失效，或地址被手写时有出入。',
    en: 'Nothing is served at this address. The link may be stale, or the address may have been typed from memory.',
  },
  'notFound.back': { zh: '返回工作台', en: 'Back to the workbench' },

  'error.title': { zh: '页面加载失败', en: 'This page failed to load' },
  'error.unknown': { zh: '发生未知错误，请刷新页面重试', en: 'Something went wrong. Reload the page to try again.' },
  'error.reload': { zh: '刷新页面', en: 'Reload' },
  'error.retry': { zh: '刷新重试', en: 'Reload and retry' },

  'common.refresh': { zh: '刷新', en: 'Refresh' },
  'common.confirm': { zh: '确认', en: 'Confirm' },
  'common.cancel': { zh: '取消', en: 'Cancel' },
  'common.actions': { zh: '操作', en: 'Actions' },
  'common.empty': { zh: '暂无数据', en: 'No data' },
  'common.loadFailed': { zh: '加载失败', en: 'Could not load' },
} as const;
