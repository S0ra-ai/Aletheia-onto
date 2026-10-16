/**
 * backup —— 页面：pages/backup/BackupManager.tsx
 *
 * 两种语言都在这里，页面通过 `t('backup.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const backup: Record<string, MessageEntry> = {
  'title': { zh: '数据备份管理', en: 'Backup management' },
  'subtitle': { zh: '创建、下载和恢复 SQLite 平台库备份；服务端数据库请使用原生备份工具。', en: 'Create, download and restore backups of the SQLite platform database; for a server-side database, use its native backup tools.' },

  'createButton': { zh: '创建备份', en: 'Create backup' },
  'createSuccess': { zh: '备份创建成功', en: 'Backup created' },
  'createFailed': { zh: '创建备份失败', en: 'Could not create the backup' },
  'listFailed': { zh: '加载备份列表失败', en: 'Could not load the backup list' },
  'downloadFailed': { zh: '下载备份失败', en: 'Could not download the backup' },
  'restoreFailed': { zh: '恢复失败', en: 'Could not restore the backup' },

  'nameColumn': { zh: '备份名称', en: 'Backup' },
  'createdAtColumn': { zh: '创建时间（本地）', en: 'Created (local time)' },
  'sizeColumn': { zh: '大小', en: 'Size' },
  'downloadButton': { zh: '下载', en: 'Download' },
  'restoreButton': { zh: '恢复', en: 'Restore' },

  'restoreConfirmTitle': { zh: '确认恢复备份', en: 'Confirm restore' },
  'restoreConfirmButton': { zh: '确认恢复', en: 'Confirm restore' },
  'restorePrompt': { zh: '即将恢复备份', en: 'You are about to restore this backup:' },
  'restoreWarning': { zh: '恢复会替换当前 SQLite 平台库。请先停止服务，恢复完成后重启平台。', en: 'A restore replaces the current SQLite platform database. Stop the service first, and restart the platform when the restore finishes.' },
  'safetyCopyBefore': { zh: '恢复前平台会自动把当前库另存为一份', en: 'Before restoring, the platform saves the current database as a' },
  'safetyCopyAfter': { zh: '备份，万一恢复的不是想要的那一份，可以用它换回来。', en: 'backup, so you can switch back to it if the restored backup was not the one you wanted.' },

  'restoreSuccess': { zh: '恢复成功，请停止服务后重启平台。恢复前的平台库已存为备份 {name}', en: 'Restore complete. Stop the service and restart the platform. The platform database from before the restore was saved as backup {name}' },
  'restoreSuccessNoSnapshot': { zh: '恢复成功，请停止服务后重启平台', en: 'Restore complete. Stop the service and restart the platform' },

  // Empty state. A fresh install has no archives, and the table said 暂无数据 under a button
  // whose purpose nothing on the page had explained.
  'emptyTitle': { zh: '还没有任何备份', en: 'No backups yet' },
  'emptyBody': {
    zh: '这份备份是平台库（本体、规则、映射、决策留痕、账号）的一个快照。它不包含你接入的业务库——那些数据仍在你自己的系统里，请用它们各自的备份工具。',
    en: 'A backup here is a snapshot of the platform database: ontologies, rules, mappings, decision records and accounts. It does not contain the business systems you connected — that data stays in your own systems and needs their own backup tools.',
  },
  'emptyHint': {
    zh: '恢复会替换当前的平台库，因此替换前平台会自动把现有库另存为一份 before-restore-… 备份。归档保存在服务器的备份目录中，服务端数据库请使用原生备份工具。',
    en: 'A restore replaces the current platform database, so the platform first saves it as a before-restore-… archive. Archives live in the server’s backup directory; for a server-side database, use its native backup tools.',
  },
};
