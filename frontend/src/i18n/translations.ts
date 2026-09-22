/**
 * Translation strings for the platform.
 * Currently only zh-CN is fully supported, but structure allows expansion.
 */

export const translations = {
  zh: {
    // Common
    loading: '加载中...',
    error: '错误',
    success: '成功',
    cancel: '取消',
    confirm: '确认',
    save: '保存',
    delete: '删除',
    edit: '编辑',
    refresh: '刷新',

    // Navigation
    workbench: '工作台',
    datasource: '数据源管理',
    ontology: '本体管理',
    rules: '业务规则',
    chat: '智能体对话',
    governance: '治理审计',
    backup: '数据备份',

    // Login
    login_title: '本体改造研发平台',
    login_subtitle: '请使用平台账号登录',
    username: '用户名',
    password: '密码',
    login_button: '登录',

    // Errors
    error_401: '登录已失效，请重新登录',
    error_403: '当前角色无权执行该操作',
    error_500: '服务器错误，请稍后重试',

    // Backup
    backup_create: '创建备份',
    backup_list: '备份列表',
    backup_restore: '恢复备份',
    backup_download: '下载备份',
  },
  en: {
    // Common
    loading: 'Loading...',
    error: 'Error',
    success: 'Success',
    cancel: 'Cancel',
    confirm: 'Confirm',
    save: 'Save',
    delete: 'Delete',
    edit: 'Edit',
    refresh: 'Refresh',

    // Navigation
    workbench: 'Workbench',
    datasource: 'Data Sources',
    ontology: 'Ontology',
    rules: 'Rules',
    chat: 'Chat',
    governance: 'Governance',
    backup: 'Backup',

    // Login
    login_title: 'Ontology Platform',
    login_subtitle: 'Please login with your account',
    username: 'Username',
    password: 'Password',
    login_button: 'Login',

    // Errors
    error_401: 'Session expired, please login again',
    error_403: 'Permission denied',
    error_500: 'Server error, please try again later',

    // Backup
    backup_create: 'Create Backup',
    backup_list: 'Backup List',
    backup_restore: 'Restore Backup',
    backup_download: 'Download Backup',
  },
} as const;

export type TranslationKey = keyof typeof translations.zh;
