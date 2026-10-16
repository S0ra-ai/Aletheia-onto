/**
 * permission —— 页面：pages/permission/PermissionManager.tsx
 *
 * 两种语言都在这里，页面通过 `t('permission.…')` 取用。缺一个键会让 `t()` 渲染出
 * `⟦key⟧` 而不是空白——缺口在界面上就能看见，并由 tests/test_ui_messages.py 断言。
 */
import type { MessageEntry } from './shell';

export const permission: Record<string, MessageEntry> = {
  'loadFailed': { zh: '加载权限配置失败', en: 'Could not load the permission configuration' },
  'roleCreated': { zh: '角色创建成功', en: 'Role created' },
  'policySaved': { zh: '策略已保存', en: 'Policy saved' },
  'createFailed': { zh: '创建失败', en: 'Could not create the role' },
  'saveFailed': { zh: '保存失败', en: 'Could not save the policy' },
  'reviewApproved': { zh: '已通过', en: 'Approved' },
  'reviewRejected': { zh: '已拒绝', en: 'Rejected' },
  'reviewFailed': { zh: '审核失败', en: 'Review failed' },
  'mappingDeclared': { zh: '组映射已声明。未映射的身份会被拒绝，而不是给一个默认角色。', en: 'Group mapping declared. Unmapped identities are refused rather than given a default role.' },
  'declareFailed': { zh: '声明组映射失败', en: 'Could not declare the group mapping' },
  'mappingRemoved': { zh: '组映射已移除', en: 'Group mapping removed' },
  'removeFailed': { zh: '移除组映射失败', en: 'Could not remove the group mapping' },

  'code': { zh: '编码', en: 'Code' },
  'name': { zh: '名称', en: 'Name' },
  'description': { zh: '描述', en: 'Description' },
  'systemRole': { zh: '系统角色', en: 'System role' },
  'yes': { zh: '是', en: 'Yes' },
  'role': { zh: '角色', en: 'Role' },
  'object': { zh: '对象', en: 'Object' },
  'read': { zh: '读', en: 'Read' },
  'write': { zh: '写', en: 'Write' },
  'execute': { zh: '执行', en: 'Execute' },
  'delete': { zh: '删除', en: 'Delete' },
  'type': { zh: '类型', en: 'Type' },
  'riskLevel': { zh: '风险等级', en: 'Risk level' },
  'requiresReview': { zh: '需审核', en: 'Review required' },
  'status': { zh: '状态', en: 'Status' },
  'tool': { zh: '工具', en: 'Tool' },
  'instance': { zh: '实例', en: 'Instance' },
  'duration': { zh: '耗时', en: 'Duration' },
  'createdAt': { zh: '创建时间（UTC）', en: 'Created (UTC)' },
  'actions': { zh: '操作', en: 'Actions' },
  'approve': { zh: '通过', en: 'Approve' },
  'reject': { zh: '拒绝', en: 'Reject' },
  'confirmReject': { zh: '确认拒绝？', en: 'Reject this request?' },

  'rolesTab': { zh: '角色管理', en: 'Role management' },
  'roleList': { zh: '角色列表', en: 'Roles' },
  'newRole': { zh: '新建角色', en: 'New role' },
  'policiesTab': { zh: '权限策略', en: 'Permission policies' },
  'newPolicy': { zh: '新建策略', en: 'New policy' },
  'newPolicyTitle': { zh: '新建权限策略', en: 'New permission policy' },
  'toolsTab': { zh: '工具定义', en: 'Tool definitions' },
  'registeredTools': { zh: '已注册工具', en: 'Registered tools' },
  'ssoTab': { zh: 'SSO 组映射', en: 'SSO group mappings' },
  'ssoCard': { zh: '单点登录', en: 'Single sign-on' },
  'declareMapping': { zh: '声明组映射', en: 'Declare a group mapping' },
  'pendingReviews': { zh: '待审核', en: 'Pending review' },
  'pendingExecutions': { zh: '待审核工具执行', en: 'Tool executions pending review' },

  // Empty states. A fresh platform has no rows in any of these three tables, and antd's
  // default 暂无数据 says the same thing about all of them: nothing, and nothing about why.
  // Each of these names where the rows come from, because a reader who has just arrived
  // cannot tell "unused" from "broken" and has no way to find out from the table.
  'noRolesTitle': { zh: '还没有自定义角色', en: 'No custom roles yet' },
  'noRolesBody': {
    zh: '平台自带 admin、本体工程师、业务专家、操作员、分析员、智能体六个内置角色，它们出现在账号与策略的选择框里，但不在这张表中。',
    en: 'The platform ships six built-in roles — admin, ontology engineer, business expert, operator, analyst and agent. They appear in the account and policy pickers but not in this table.',
  },
  'noRolesHint': {
    zh: '这张表列出的是额外增加的角色。当内置角色的权限范围不适用时（例如只有一类合同可以查看的「合同专员」），在这里新建一个，再为它配置策略。',
    en: 'This table lists roles you add. Create one here when a built-in role is too broad — a contracts clerk who may read one category, say — and then give it policies.',
  },

  'noPoliciesTitle': { zh: '还没有权限策略', en: 'No permission policies yet' },
  'noPoliciesBody': {
    zh: '策略决定某个角色能读、写、执行、删除哪个业务对象的数据。没有策略时，除 admin 外没有任何角色能访问业务对象。',
    en: 'A policy decides which business object’s data a role may read, write, execute on or delete. With no policies, no role other than admin can reach a business object at all.',
  },
  'noPoliciesHint': {
    zh: '策略依附于已发布本体中的业务对象，所以先在「数据接入」扫描业务库、在「知识建模」生成本体并发布，再回到这里。',
    en: 'A policy attaches to a business object in a published ontology — scan the source under Data sources, generate and publish an ontology under Modelling, then come back here.',
  },

  'noToolsTitle': { zh: '还没有注册工具', en: 'No tools registered' },
  'noToolsBody': {
    zh: '工具是智能体可以调用的动作，每个都指向一个已登记的业务 API 操作。注册时声明它的风险等级，高风险工具的执行会先进入待审核队列。',
    en: 'A tool is an action an agent may take, and each one points at a registered business API operation. Its risk level is declared when it is registered; a high-risk execution is held for review first.',
  },
  'noToolsHint': {
    zh: '先在「数据接入」的详情页导入业务系统的 OpenAPI 描述（或手工登记接口），接口才会出现在这里供注册。',
    en: 'Import the business system’s OpenAPI description — or register an interface by hand — on the data source’s detail page first; only then can it be registered here.',
  },
  'goToDataSources': { zh: '去数据接入', en: 'Go to data sources' },
  'goToOntology': { zh: '去知识建模', en: 'Go to modelling' },

  'ssoUnknownTitle': { zh: '无法读取 SSO 状态', en: 'Could not read the SSO status' },
  'ssoUnknownDesc': { zh: '这不表示 SSO 已启用或已关闭，只表示这次读取失败。请刷新重试；若持续失败，查看服务端日志。', en: 'This does not mean SSO is on or off; it means this read failed. Reload to try again, and check the server logs if it keeps failing.' },
  'ssoDisabledTitle': { zh: '未启用 SSO', en: 'SSO is not enabled' },
  'ssoDisabledDesc': { zh: 'SSO 由环境变量配置（ONTOLOGY_SSO_ISSUER／ONTOLOGY_SSO_AUDIENCE／ONTOLOGY_SSO_SECRET），三项缺一即视为关闭。启用后在这里声明组到角色的映射。', en: 'SSO is configured by environment variables (ONTOLOGY_SSO_ISSUER / ONTOLOGY_SSO_AUDIENCE / ONTOLOGY_SSO_SECRET); it is off unless all three are set. Once enabled, declare group-to-role mappings here.' },
  'ssoEnabledTitle': { zh: 'SSO 已启用：身份由提供方断言，权限由平台决定（已映射 {count} 个组）', en: 'SSO is enabled: the provider asserts identity, the platform decides permissions ({count} groups mapped)' },
  'ssoIssuerLine': { zh: '签发方：{issuer}　受众：{audience}　算法：{algorithm}（取自配置，绝不取自令牌头）', en: 'Issuer: {issuer}  Audience: {audience}  Algorithm: {algorithm} (read from configuration, never from the token header)' },
  'ssoClaimsLine': { zh: '组声明：{group}　用户标识声明：{username}', en: 'Group claim: {group}  Username claim: {username}' },
  'noMappingsTitle': { zh: '尚未声明任何组映射：所有 SSO 登录都会被拒绝', en: 'No group mappings declared yet: every SSO sign-in will be refused' },
  'noMappingsDesc': { zh: '这是刻意设计——未映射的身份不给默认角色，否则目录里的每位员工都会被静默授予「读取平台可达的全部业务对象」。', en: 'This is deliberate: an unmapped identity is given no default role; otherwise every employee in the directory would be silently granted "read every business object the platform can reach".' },

  'providerGroup': { zh: '提供方组', en: 'Provider group' },
  'platformRole': { zh: '平台角色', en: 'Platform role' },
  'note': { zh: '备注', en: 'Note' },
  'confirmRemoveMapping': { zh: '移除该组映射？未映射的组将无法登录。', en: 'Remove this group mapping? Unmapped groups will not be able to sign in.' },
  'remove': { zh: '移除', en: 'Remove' },

  'providerGroupRequired': { zh: '请填写提供方组名', en: 'Enter the provider group name' },
  'providerGroupHint': { zh: '取自令牌里的组声明，需与提供方完全一致。', en: 'Taken from the token\'s group claim; it must match the provider\'s group name exactly.' },
  'providerGroupExample': { zh: '如 engineering', en: 'e.g. engineering' },
  'roleRequired': { zh: '请选择角色', en: 'Select a role' },
  'roleOption': { zh: '{name}（{code}）', en: '{name} ({code})' },
  'notePlaceholder': { zh: '为什么这个组对应这个角色', en: 'Why this group maps to this role' },
  'roleCode': { zh: '角色编码', en: 'Role code' },
  'roleCodeExample': { zh: '如 manager', en: 'e.g. manager' },
  'roleName': { zh: '角色名称', en: 'Role name' },
  'roleNameExample': { zh: '部门经理', en: 'Department manager' },
  'optional': { zh: '可选', en: 'Optional' },
  'objectCode': { zh: '业务对象编码', en: 'Business object code' },
  'objectCodeExample': { zh: '如 contract, equipment', en: 'e.g. contract, equipment' },
  'selectRole': { zh: '选择角色', en: 'Select a role' },
};
