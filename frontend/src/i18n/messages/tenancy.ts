/**
 * tenancy —— 页面：pages/tenancy/TenancyManager.tsx
 *
 * 两种语言都在这里，页面通过 `t('tenancy.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const tenancy: Record<string, MessageEntry> = {
  'title': { zh: '租户管理', en: 'Tenant management' },

  'introBefore': { zh: '多租户为', en: 'Multi-tenancy is an ' },
  'introOptional': { zh: '可选', en: 'optional' },
  'introAfter': { zh: '能力：单租户部署下这里为空是预期结果，不是故障。每租户独立 schema，关键表另带 tenant_id 作为双保险；配额存放在基础库而非租户库——存在租户库里的配额是租户可以自己改的配额。', en: ' capability: on a single-tenant deployment an empty list here is the expected result, not a fault. Each tenant gets its own schema, and key tables carry tenant_id as a second line of defence; quotas live in the base database rather than the tenant database — a quota stored in the tenant database is a quota the tenant can change.' },

  'loadFailedTitle': { zh: '读取失败', en: 'Load failed' },
  'loadTenantsFailed': { zh: '获取租户列表失败', en: 'Could not load the tenant list' },
  'loadDetailFailed': { zh: '读取租户信息失败', en: 'Could not read the tenant details' },
  'createSuccess': { zh: '租户 {tenant} 已开通，schema：{schema}', en: 'Tenant {tenant} provisioned, schema: {schema}' },
  'createFailed': { zh: '开通租户失败', en: 'Could not provision the tenant' },
  'quotaSuccess': { zh: '配额已声明。配额存放在基础库，租户无法自行修改。', en: 'Quota declared. Quotas live in the base database, so tenants cannot change them.' },
  'quotaFailed': { zh: '声明配额失败', en: 'Could not declare the quota' },
  'isolationModel': { zh: '隔离模型：{model}（平台库：{database}）', en: 'Isolation model: {model} (platform database: {database})' },

  'tenantList': { zh: '租户列表', en: 'Tenants' },
  'createTenant': { zh: '开通租户', en: 'Provision a tenant' },
  'emptyTenants': { zh: '当前部署未开通任何租户（单租户模式）', en: 'No tenants have been provisioned on this deployment (single-tenant mode)' },
  'column.tenant': { zh: '租户', en: 'Tenant' },
  'selected': { zh: '已选中', en: 'Selected' },
  'viewUsage': { zh: '查看用量与配额', en: 'View usage and quotas' },

  'usageTitle': { zh: '资源用量：{tenant}', en: 'Resource usage: {tenant}' },
  'totalRows': { zh: '总行数', en: 'Total rows' },
  'noUsage': { zh: '暂无用量数据', en: 'No usage data yet' },

  'quotaTitle': { zh: '配额', en: 'Quotas' },
  'declareQuota': { zh: '声明配额', en: 'Declare a quota' },
  'quotaIntroBefore': { zh: '未声明配额的资源为', en: 'A resource with no declared quota is ' },
  'unlimited': { zh: '不限量', en: 'Unlimited' },
  'quotaIntroAfter': { zh: '（而不是 0）——后者会让既有部署在这个特性上线的瞬间停止接受写入。用量按真实行数统计，不维护计数器。', en: ' (not 0) — treating it as 0 would stop an existing deployment from accepting writes the moment this feature goes live. Usage is counted from real rows; no counters are maintained.' },
  // What each limitable resource is, keyed by the resource code the API uses
  // (`quotas.QUOTA_RESOURCES`). The server sends its own Chinese description beside the code
  // and the console falls back to it for a resource this build does not know -- a deployment
  // that adds one through an extension should still see something.
  'resource.data_sources': {
    zh: '接入的传统业务系统数量',
    en: 'Legacy systems connected',
  },
  'resource.ontologies': { zh: '本体数量（含各版本）', en: 'Ontologies, versions included' },
  'resource.business_rules': { zh: '业务规则数量', en: 'Business rules' },
  'resource.knowledge_documents': { zh: '知识文档数量', en: 'Knowledge documents' },
  'resource.knowledge_entries': {
    zh: '知识条目数量（切分后的条款）',
    en: 'Knowledge entries (the clauses a document splits into)',
  },
  'resource.conversations': { zh: '会话数量', en: 'Conversations' },
  'resource.decision_records': { zh: '判定留痕数量', en: 'Decision records' },
  'resource': { zh: '资源', en: 'Resource' },
  'countTable': { zh: '计数表', en: 'Count table' },
  'current': { zh: '当前', en: 'Current' },
  'limit': { zh: '上限', en: 'Limit' },
  'remaining': { zh: '剩余', en: 'Remaining' },
  'exceeded': { zh: '已超出', en: 'Exceeded' },

  'idempotentTitle': { zh: '开通是幂等的', en: 'Provisioning is idempotent' },
  'idempotentHint': { zh: '重复执行不会破坏已有数据，因此可以放心地把它写进部署流程。', en: 'Running it again does not damage existing data, so it can safely be part of a deployment pipeline.' },
  'tenantIdLabel': { zh: '租户标识', en: 'Tenant identifier' },
  'tenantIdRequired': { zh: '请填写租户标识', en: 'Enter a tenant identifier' },
  'tenantIdHint': { zh: '用作 schema 名，请使用字母、数字与下划线。', en: 'Used as the schema name; use letters, digits and underscores.' },
  'quotaModalTitle': { zh: '为 {tenant} 声明配额', en: 'Declare a quota for {tenant}' },
  'resourceRequired': { zh: '请选择资源', en: 'Choose a resource' },
  'resourceOption': { zh: '{resource}（计数表 {table}）', en: '{resource} (count table {table})' },
  'limitRequired': { zh: '请填写上限', en: 'Enter a limit' },
  'limitHint': { zh: '设置为 0 表示不允许创建该类数据；留空不适用于本表单——不限量是「不声明」的结果。', en: 'Set to 0 to disallow creating this kind of data; leaving it blank is not an option here — Unlimited is the result of not declaring a quota at all.' },
  'note': { zh: '备注', en: 'Note' },
  'notePlaceholder': { zh: '为什么是这个数字', en: 'Why this number' },
};
