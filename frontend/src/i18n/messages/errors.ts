/**
 * errors —— 组件：error-boundary/ErrorBoundary.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('errors.…')`。
 */
import type { MessageEntry } from './shell';

export const errors: Record<string, MessageEntry> = {
  'title': { zh: '页面加载失败', en: 'This page could not be loaded' },
  'unknown': { zh: '发生未知错误，请刷新页面重试', en: 'Something went wrong. Reload the page to try again.' },
  'unknownShort': { zh: '发生未知错误', en: 'Something went wrong.' },

  'reload': { zh: '刷新页面', en: 'Reload' },
  'retry': { zh: '刷新重试', en: 'Reload and retry' },
};
