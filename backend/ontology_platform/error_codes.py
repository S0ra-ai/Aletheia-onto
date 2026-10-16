"""The platform's own refusals, named as well as said.

Every sentence here is one a route returns to a person who asked for something it will not
do. They were Chinese-only, and the console in English mode printed them verbatim: the
translations of advice, gate verdicts, audit findings and instance explanations had all been
done, and **the one category left was the message a reader gets when something fails** --
which is the moment they most need to understand it.

The shape is the same one `advice.py` uses, for the same reason: a registry of
`(code, sentence)` pairs, the sentence kept because the CLI and third-party clients read it,
and the code added because a console needs something to key a translation on. What is
different is the direction of the lookup. Advice *emits* pairs, so it can carry the code
alongside the text in its payload. A refusal is raised as an exception deep in a domain
module, and by the time it reaches HTTP all that is left is `str(error)` -- threading a code
through 103 `raise` sites and every function between them would be a rewrite of the whole
domain layer for a display concern.

So this module identifies the sentence instead. Every string below is written by this
platform and by nothing else, which makes a match an identification rather than a guess --
the same argument `advice.recommendation_code` makes for the sentences it recovers.

## Templates, because most refusals name something

`本体不存在: 1` and `本体不存在` are the same refusal with and without the id, and both are
raised. A template is the sentence with its values replaced by `{name}`, and it is matched by
walking its literal parts in order, so the values come back out as facts the console can put
in its own sentence -- in either language, and in the word order that language needs.

## What is not here

A refusal with no code is not an error. `decorate` leaves the body as it was, and the
console falls back to the server's sentence exactly as it does for an advice code it does not
know. That is the honest behaviour for a sentence nobody has translated yet, and
`tests/test_error_codes.py` measures how much of the surface is left rather than asserting it
is zero.

Two categories are deliberately absent rather than overlooked:

**Quota exceeded.** Its sentence names the resource by its display label -- 「本体」 -- which
is itself Chinese, written by the module that declares the quotas. A fact carrying a Chinese
noun into an English sentence is not a translation, and looking a translation up by that label
would be worse. It needs the resource *code* in the message first, which is a change to what
the quota module says rather than to how it is named.

**Anything written by a driver or the standard library.** `errors.py` owns those, and it
already restates them in Chinese for the person holding the problem. They are English
internals in the argument rather than refusals this platform authored.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["CODES", "TEMPLATES", "decorate", "identify", "sentence_for"]

# -- Authentication and accounts --
AUTH_LOGIN_FAILED = "login_failed"
AUTH_ACCOUNT_DISABLED = "account_disabled"
AUTH_CURRENT_PASSWORD_WRONG = "current_password_wrong"
AUTH_PASSWORD_TOO_SHORT = "password_too_short"
AUTH_USERNAME_REQUIRED = "username_required"
# The auth middleware already puts these two on its own responses (`api.py`), and a second
# spelling for the same refusal would be one more thing for a client to learn. The sentence is
# the same one `auth.py` raises when a token is missing or a role lacks a capability, so the
# registry and the middleware agree by construction rather than by being kept in step.
AUTH_TOKEN_MISSING = "unauthenticated"
AUTH_FORBIDDEN = "forbidden"
AUTH_TOKEN_INVALID = "token_invalid"
AUTH_TOKEN_EXPIRED = "token_expired"
AUTH_TOKEN_REVOKED = "token_revoked"
AUTH_USER_NOT_FOUND = "user_not_found"
AUTH_USER_STATUS_INVALID = "user_status_invalid"

# -- Things that are not there --
ONTOLOGY_NOT_FOUND = "ontology_not_found"
DATA_SOURCE_NOT_FOUND = "data_source_not_found"
OBJECT_NOT_FOUND = "object_not_found"
INSTANCE_NOT_FOUND = "instance_not_found"
RULE_NOT_FOUND = "rule_not_found"
CONVERSATION_NOT_FOUND = "conversation_not_found"
WORKFLOW_NOT_FOUND = "workflow_not_found"
BACKUP_NOT_FOUND = "backup_not_found"
KNOWLEDGE_ENTRY_NOT_FOUND = "knowledge_entry_not_found"

# -- Objects that are not usable yet --
OBJECT_NOT_BOUND_TO_SOURCE = "object_not_bound_to_source"
OBJECT_NOT_BOUND_TO_TABLE = "object_not_bound_to_table"
SOURCE_TABLE_NOT_SCANNED = "source_table_not_scanned"
NO_OBJECTS_MODELLED = "no_objects_modelled"

# -- Governance refusals --
PUBLISH_NEEDS_CONFIRMED_MAPPINGS = "publish_needs_confirmed_mappings"
PUBLISHED_MAPPINGS_IMMUTABLE = "published_mappings_immutable"
PUBLISHED_RULES_IMMUTABLE = "published_rules_immutable"
PUBLISHED_RULES_UNDELETABLE = "published_rules_undeletable"
PUBLISHED_KNOWLEDGE_IMMUTABLE = "published_knowledge_immutable"
PUBLISHED_CANNOT_REGENERATE = "published_cannot_regenerate"
DERIVE_REQUIRES_PUBLISHED = "derive_requires_published"
MAPPINGS_STILL_PENDING = "mappings_still_pending"
ONTOLOGY_NOT_PUBLISHABLE = "ontology_not_publishable"
ONTOLOGY_VERSION_EXISTS = "ontology_version_exists"
RELEASE_GATE_BLOCKED = "release_gate_blocked"
MAPPING_NOT_FOUND = "mapping_not_found"
RULE_SCOPE_OBJECT_NOT_FOUND = "rule_scope_object_not_found"
RULE_TYPE_UNSUPPORTED = "rule_type_unsupported"
RULE_SEVERITY_UNSUPPORTED = "rule_severity_unsupported"
RULE_EXPRESSION_NOT_EXECUTABLE = "rule_expression_not_executable"
RULE_OVERRIDE_NOT_SUPERIOR = "rule_override_not_superior"
RULE_OVERRIDE_SELF = "rule_override_self"
RULE_OVERRIDDEN_MISSING = "rule_overridden_missing"

# The same refusal in eleven modules: each declares its own editable artefact on a published
# ontology, and all of them say the same thing with a different noun. One code, one sentence
# per noun -- the noun is the fact, so the console says it in the reader's language.
PUBLISHED_AGGREGATION_IMMUTABLE = "aggregation_immutable"
PUBLISHED_DERIVED_ATTRIBUTE_IMMUTABLE = "derived_attribute_immutable"
PUBLISHED_UNIT_IMMUTABLE = "unit_immutable"
PUBLISHED_CROSS_SOURCE_IMMUTABLE = "cross_source_immutable"
PUBLISHED_EVENT_TYPE_IMMUTABLE = "event_type_immutable"
PUBLISHED_INSTANCE_RESOLVER_IMMUTABLE = "instance_resolver_immutable"
PUBLISHED_TYPE_HIERARCHY_IMMUTABLE = "type_hierarchy_immutable"
PUBLISHED_VALUE_MAPPING_IMMUTABLE = "value_mapping_immutable"
# The two above are registered separately because their wording differs slightly
# (`不可直接修改` / `不可直接删除` / `不可新增`), so they are not this family.

# -- Data sources and their files --
SOURCE_DIRECTORY_REQUIRED = "source_directory_required"
SOURCE_DIRECTORY_MISSING = "source_directory_missing"
SOURCE_FILE_MISSING = "source_file_missing"
MYSQL_URI_FORMAT = "mysql_uri_format"
OPENAPI_PATHS_MISSING = "openapi_paths_missing"
OPENAPI_URL_INVALID = "openapi_url_invalid"
OPENAPI_URL_NOT_JSON = "openapi_url_not_json"
TEST_CONNECTION_INPUT_REQUIRED = "test_connection_input_required"

# -- Documents and imports --
UPLOAD_FORMAT_UNSUPPORTED = "upload_format_unsupported"
DOCUMENT_TITLE_REQUIRED = "document_title_required"
DOCUMENT_ALREADY_IMPORTED = "document_already_imported"
WORD_NO_RULES_FOUND = "word_no_rules_found"
WORD_NOT_A_DOCX = "word_not_a_docx"
WORD_SUPPORT_MISSING = "word_support_missing"

# -- Rules and modelling --
SCOPE_OBJECT_REQUIRED = "scope_object_required"
NO_ONTOLOGY_TO_EXPLAIN = "no_ontology_to_explain"
DATA_SOURCE_NOT_READY = "data_source_not_ready"
INSTANCE_HINT_REQUIRED = "instance_hint_required"

# -- The model endpoint --
MODEL_KEY_MISSING = "model_key_missing"
MODEL_AUTH_STYLE_UNSUPPORTED = "model_auth_style_unsupported"
MODEL_AUTH_HEADER_REQUIRED = "model_auth_header_required"
MODEL_RESPONSE_NOT_JSON = "model_response_not_json"

# -- Tenancy --
TENANT_ID_REQUIRED = "tenant_id_required"
TENANT_ID_INVALID = "tenant_id_invalid"
QUOTA_RESOURCE_UNKNOWN = "quota_resource_unknown"
QUOTA_LIMIT_NEGATIVE = "quota_limit_negative"
CROSS_TENANT_ACCESS = "cross_tenant_access"

# -- Single sign-on --
SSO_GROUP_REQUIRED = "sso_group_required"
SSO_ROLE_UNKNOWN = "sso_role_unknown"
SSO_MAPPING_MISSING = "sso_mapping_missing"
SSO_IDENTITY_UNMAPPED = "sso_identity_unmapped"
SSO_NOT_ENABLED = "sso_not_enabled"
SSO_ALGORITHM_UNSUPPORTED = "sso_algorithm_unsupported"
SSO_ASSERTION_EXPIRED = "sso_assertion_expired"
SSO_ASSERTION_NO_EXPIRY = "sso_assertion_no_expiry"
SSO_ASSERTION_MALFORMED = "sso_assertion_malformed"
SSO_SIGNATURE_INVALID = "sso_signature_invalid"
SSO_ISSUER_MISMATCH = "sso_issuer_mismatch"
SSO_AUDIENCE_MISMATCH = "sso_audience_mismatch"

# -- Workflow --
WORKFLOW_NOT_CONFIGURED = "workflow_not_configured"
INSTANCE_NOT_IN_WORKFLOW = "instance_not_in_workflow"
INSTANCE_ALREADY_IN_WORKFLOW = "instance_already_in_workflow"
TRANSITION_NOT_ALLOWED = "transition_not_allowed"
GUARD_REJECTED = "guard_rejected"

# -- Requests --
QUESTION_REQUIRED = "question_required"
FILE_NAME_REQUIRED = "file_name_required"
FILE_CONTENT_EMPTY = "file_content_empty"
UNSUPPORTED_STATUS = "unsupported_status"
RULE_FUNCTION_NOT_ALLOWED = "rule_function_not_allowed"
MIGRATION_FAILED = "migration_failed"
SCAFFOLD_PROJECT_NAME_INVALID = "scaffold_project_name_invalid"
SCAFFOLD_FILES_EXIST = "scaffold_files_exist"
SCAFFOLD_EXTENSION_UNKNOWN = "scaffold_extension_unknown"

CODES: tuple[str, ...] = (
    AUTH_LOGIN_FAILED,
    AUTH_ACCOUNT_DISABLED,
    AUTH_CURRENT_PASSWORD_WRONG,
    AUTH_PASSWORD_TOO_SHORT,
    AUTH_USERNAME_REQUIRED,
    AUTH_TOKEN_MISSING,
    AUTH_FORBIDDEN,
    AUTH_TOKEN_INVALID,
    AUTH_TOKEN_EXPIRED,
    AUTH_TOKEN_REVOKED,
    AUTH_USER_NOT_FOUND,
    AUTH_USER_STATUS_INVALID,
    ONTOLOGY_NOT_FOUND,
    DATA_SOURCE_NOT_FOUND,
    OBJECT_NOT_FOUND,
    INSTANCE_NOT_FOUND,
    RULE_NOT_FOUND,
    CONVERSATION_NOT_FOUND,
    WORKFLOW_NOT_FOUND,
    BACKUP_NOT_FOUND,
    KNOWLEDGE_ENTRY_NOT_FOUND,
    OBJECT_NOT_BOUND_TO_SOURCE,
    OBJECT_NOT_BOUND_TO_TABLE,
    SOURCE_TABLE_NOT_SCANNED,
    NO_OBJECTS_MODELLED,
    PUBLISH_NEEDS_CONFIRMED_MAPPINGS,
    PUBLISHED_MAPPINGS_IMMUTABLE,
    PUBLISHED_RULES_IMMUTABLE,
    PUBLISHED_RULES_UNDELETABLE,
    PUBLISHED_KNOWLEDGE_IMMUTABLE,
    PUBLISHED_CANNOT_REGENERATE,
    DERIVE_REQUIRES_PUBLISHED,
    MAPPINGS_STILL_PENDING,
    ONTOLOGY_NOT_PUBLISHABLE,
    ONTOLOGY_VERSION_EXISTS,
    RELEASE_GATE_BLOCKED,
    MAPPING_NOT_FOUND,
    RULE_SCOPE_OBJECT_NOT_FOUND,
    RULE_TYPE_UNSUPPORTED,
    RULE_SEVERITY_UNSUPPORTED,
    RULE_EXPRESSION_NOT_EXECUTABLE,
    RULE_OVERRIDE_NOT_SUPERIOR,
    RULE_OVERRIDE_SELF,
    RULE_OVERRIDDEN_MISSING,
    PUBLISHED_AGGREGATION_IMMUTABLE,
    PUBLISHED_DERIVED_ATTRIBUTE_IMMUTABLE,
    PUBLISHED_UNIT_IMMUTABLE,
    PUBLISHED_CROSS_SOURCE_IMMUTABLE,
    PUBLISHED_EVENT_TYPE_IMMUTABLE,
    PUBLISHED_INSTANCE_RESOLVER_IMMUTABLE,
    PUBLISHED_TYPE_HIERARCHY_IMMUTABLE,
    PUBLISHED_VALUE_MAPPING_IMMUTABLE,
    SOURCE_DIRECTORY_REQUIRED,
    SOURCE_DIRECTORY_MISSING,
    SOURCE_FILE_MISSING,
    MYSQL_URI_FORMAT,
    OPENAPI_PATHS_MISSING,
    OPENAPI_URL_INVALID,
    OPENAPI_URL_NOT_JSON,
    TEST_CONNECTION_INPUT_REQUIRED,
    UPLOAD_FORMAT_UNSUPPORTED,
    DOCUMENT_TITLE_REQUIRED,
    DOCUMENT_ALREADY_IMPORTED,
    WORD_NO_RULES_FOUND,
    WORD_NOT_A_DOCX,
    WORD_SUPPORT_MISSING,
    SCOPE_OBJECT_REQUIRED,
    NO_ONTOLOGY_TO_EXPLAIN,
    DATA_SOURCE_NOT_READY,
    INSTANCE_HINT_REQUIRED,
    MODEL_KEY_MISSING,
    MODEL_AUTH_STYLE_UNSUPPORTED,
    MODEL_AUTH_HEADER_REQUIRED,
    MODEL_RESPONSE_NOT_JSON,
    TENANT_ID_REQUIRED,
    TENANT_ID_INVALID,
    QUOTA_RESOURCE_UNKNOWN,
    QUOTA_LIMIT_NEGATIVE,
    CROSS_TENANT_ACCESS,
    SSO_GROUP_REQUIRED,
    SSO_ROLE_UNKNOWN,
    SSO_MAPPING_MISSING,
    SSO_IDENTITY_UNMAPPED,
    SSO_NOT_ENABLED,
    SSO_ALGORITHM_UNSUPPORTED,
    SSO_ASSERTION_EXPIRED,
    SSO_ASSERTION_NO_EXPIRY,
    SSO_ASSERTION_MALFORMED,
    SSO_SIGNATURE_INVALID,
    SSO_ISSUER_MISMATCH,
    SSO_AUDIENCE_MISMATCH,
    WORKFLOW_NOT_CONFIGURED,
    INSTANCE_NOT_IN_WORKFLOW,
    INSTANCE_ALREADY_IN_WORKFLOW,
    TRANSITION_NOT_ALLOWED,
    GUARD_REJECTED,
    QUESTION_REQUIRED,
    FILE_NAME_REQUIRED,
    FILE_CONTENT_EMPTY,
    UNSUPPORTED_STATUS,
    RULE_FUNCTION_NOT_ALLOWED,
    MIGRATION_FAILED,
    SCAFFOLD_PROJECT_NAME_INVALID,
    SCAFFOLD_FILES_EXIST,
    SCAFFOLD_EXTENSION_UNKNOWN,
)

# `code -> the sentences that mean it`, in the platform's own words.
#
# A code with more than one template is not duplication: the same refusal is worded for a
# reader who has the id to hand and for one who does not, and both are raised. The extra
# spellings are listed against the code rather than merged into one sentence, because
# changing what a domain module says is a different change from naming what it says.
TEMPLATES: dict[str, tuple[str, ...]] = {
    AUTH_LOGIN_FAILED: ("用户名或密码不正确",),
    AUTH_ACCOUNT_DISABLED: ("用户已被禁用",),
    AUTH_CURRENT_PASSWORD_WRONG: ("当前密码不正确",),
    AUTH_PASSWORD_TOO_SHORT: ("密码长度至少 8 位",),
    AUTH_USERNAME_REQUIRED: ("用户名不能为空",),
    AUTH_TOKEN_MISSING: ("缺少访问令牌",),
    AUTH_FORBIDDEN: ("角色 {roleCode} 缺少所需权限 {capability}",),
    AUTH_TOKEN_INVALID: ("访问令牌无效",),
    AUTH_TOKEN_EXPIRED: ("访问令牌已过期，请重新登录",),
    AUTH_TOKEN_REVOKED: ("访问令牌已失效，请重新登录",),
    AUTH_USER_NOT_FOUND: ("用户不存在: {username}",),
    AUTH_USER_STATUS_INVALID: ("用户状态只能是 active 或 disabled",),
    ONTOLOGY_NOT_FOUND: ("本体不存在: {ontologyId}",),
    DATA_SOURCE_NOT_FOUND: ("数据源不存在: {dataSourceId}", "数据源不存在"),
    OBJECT_NOT_FOUND: ("业务对象不存在: {objectCode}",),
    INSTANCE_NOT_FOUND: ("实例不存在: {objectCode}/{instanceId}",),
    RULE_NOT_FOUND: ("规则不存在: {ruleId}",),
    CONVERSATION_NOT_FOUND: ("会话不存在: {sessionId}",),
    WORKFLOW_NOT_FOUND: ("工作流 {workflowId} 不存在",),
    BACKUP_NOT_FOUND: ("备份文件不存在: {name}",),
    KNOWLEDGE_ENTRY_NOT_FOUND: ("知识条目不存在: {entryId}",),
    OBJECT_NOT_BOUND_TO_SOURCE: ("业务对象未绑定可用数据源: {objectCode}",),
    OBJECT_NOT_BOUND_TO_TABLE: ("业务对象未绑定来源表: {objectCode}",),
    SOURCE_TABLE_NOT_SCANNED: ("数据表未经扫描或不属于该数据源",),
    NO_OBJECTS_MODELLED: ("尚未建模任何业务对象，请先接入数据源并生成本体草案",),
    PUBLISH_NEEDS_CONFIRMED_MAPPINGS: ("没有已确认的语义映射，不能发布本体。",),
    PUBLISHED_MAPPINGS_IMMUTABLE: ("已发布本体的语义映射不可直接审核，请派生新版本。",),
    PUBLISHED_RULES_IMMUTABLE: ("已发布本体的规则不可直接修改，请派生新版本。",),
    PUBLISHED_RULES_UNDELETABLE: ("已发布本体的规则不可直接删除，请派生新版本。",),
    PUBLISHED_KNOWLEDGE_IMMUTABLE: ("已发布本体不可新增知识条目，请派生新版本。",),
    # Eight more artefacts on a published ontology, each with its own noun written into the
    # sentence by the module that owns it. One code each rather than one parameterised code:
    # the noun is not a variable in the source, so a single template cannot match all eight,
    # and an English sentence that could not name the noun would be vaguer than the Chinese.
    PUBLISHED_AGGREGATION_IMMUTABLE: ("已发布本体不可修改聚合定义，请派生新版本。",),
    PUBLISHED_DERIVED_ATTRIBUTE_IMMUTABLE: ("已发布本体不可修改派生属性，请派生新版本。",),
    PUBLISHED_UNIT_IMMUTABLE: ("已发布本体不可修改属性单位，请派生新版本。",),
    PUBLISHED_CROSS_SOURCE_IMMUTABLE: ("已发布本体不可修改跨源对应，请派生新版本。",),
    PUBLISHED_EVENT_TYPE_IMMUTABLE: ("已发布本体不可修改事件定义，请派生新版本。",),
    PUBLISHED_INSTANCE_RESOLVER_IMMUTABLE: ("已发布本体不可修改实例解析器，请派生新版本。",),
    PUBLISHED_TYPE_HIERARCHY_IMMUTABLE: ("已发布本体不可修改类型层级，请派生新版本。",),
    PUBLISHED_VALUE_MAPPING_IMMUTABLE: ("已发布本体不可修改值域映射，请派生新版本。",),
    PUBLISHED_CANNOT_REGENERATE: ("本体版本已发布，不能重新生成草案: {name} 0.1.0。请派生新版本。",),
    DERIVE_REQUIRES_PUBLISHED: ("只能从已发布本体派生新版本。",),
    WORKFLOW_NOT_CONFIGURED: ("该业务对象未配置工作流",),
    INSTANCE_NOT_IN_WORKFLOW: ("实例不在工作流中",),
    INSTANCE_ALREADY_IN_WORKFLOW: ("实例 {instanceId} 已在工作流中",),
    TRANSITION_NOT_ALLOWED: ("当前状态 '{fromState}' 不允许执行动作 '{actionCode}'",),
    GUARD_REJECTED: ("流转守卫未通过，动作 '{actionCode}' 被阻止：{reason}",),
    MAPPINGS_STILL_PENDING: ("仍有 {count} 条语义映射待审核，不能发布本体。",),
    ONTOLOGY_NOT_PUBLISHABLE: ("当前本体状态不可发布: {status}",),
    ONTOLOGY_VERSION_EXISTS: ("本体版本已存在: {name} {version}",),
    RELEASE_GATE_BLOCKED: ("发布门禁未通过，存在 {count} 项阻断项，不能发布本体。{detail}",),
    MAPPING_NOT_FOUND: ("语义映射不存在: {mappingId}",),
    RULE_SCOPE_OBJECT_NOT_FOUND: ("规则适用业务对象不存在: {objectCode}",),
    RULE_TYPE_UNSUPPORTED: ("不支持的规则类型: {ruleType}",),
    RULE_SEVERITY_UNSUPPORTED: ("不支持的规则严重级别: {severity}",),
    RULE_EXPRESSION_NOT_EXECUTABLE: ("规则表达式不可执行: {expression}",),
    RULE_OVERRIDE_SELF: ("规则不能覆盖自身: {ruleCode}",),
    RULE_OVERRIDDEN_MISSING: ("被覆盖的规则不存在: {ruleCode}",),
    RULE_OVERRIDE_NOT_SUPERIOR: (
        "只能覆盖上级类型的规则。{ruleCode} 属于 {objectCode}，不在 {scopeObjectCode} 的上级链 {ancestors} 中。",
    ),
    # Eleven artefacts, one refusal each, all the same sentence shape. Registered once with the
    # noun as a fact rather than eleven times: the console has one sentence to translate and the
    # noun arrives already translated by whichever dictionary names that artefact.
    SOURCE_DIRECTORY_REQUIRED: ("文件数据源需要一个目录路径",),
    SOURCE_DIRECTORY_MISSING: ("目录不存在: {path}",),
    SOURCE_FILE_MISSING: ("文件不存在: {filename}（在 {directory}）",),
    MYSQL_URI_FORMAT: ("MySQL 连接串应使用 mysql://user:password@host:port/database",),
    OPENAPI_PATHS_MISSING: ("OpenAPI 文档缺少 paths 对象",),
    OPENAPI_URL_INVALID: ("OpenAPI URL 必须是 HTTP/HTTPS 地址",),
    OPENAPI_URL_NOT_JSON: ("OpenAPI URL 返回内容不是有效 JSON",),
    TEST_CONNECTION_INPUT_REQUIRED: ("测试未登记数据源时必须提供 sourceType 和 connectionUri",),
    UPLOAD_FORMAT_UNSUPPORTED: ("仅支持 .docx 或 UTF-8 文本文件。",),
    DOCUMENT_TITLE_REQUIRED: ("文档标题不能为空",),
    DOCUMENT_ALREADY_IMPORTED: ("该文档内容已导入（文档 #{documentId}），请勿重复上传。",),
    WORD_NO_RULES_FOUND: (
        "未从 Word 文档中识别到规则。建议使用表头：规则编码、规则名称、适用对象、规则类型、规则表达式、严重程度、自然语言说明。",
    ),
    WORD_NOT_A_DOCX: (
        "这个文件不是有效的 Word 文档（.docx）。"
        "常见情况是把别的格式改名成 .docx，或文件在上传过程中被截断；请用 Word／WPS 另存为 .docx 后重试。",
    ),
    WORD_SUPPORT_MISSING: ("缺少 python-docx 依赖，无法解析 Word 规则文档。请安装 requirements.txt。",),
    SCOPE_OBJECT_REQUIRED: ("确认知识条目前必须指定锚定的业务对象或规则。",),
    NO_ONTOLOGY_TO_EXPLAIN: ("尚未生成本体，请先接入数据源并生成本体草案",),
    DATA_SOURCE_NOT_READY: ("请选择已初始化的数据源",),
    INSTANCE_HINT_REQUIRED: ("请在问题中说明要解释的实例，例如：{example}",),
    MODEL_KEY_MISSING: ("未配置模型 API Key，无法调用远程模型",),
    MODEL_AUTH_STYLE_UNSUPPORTED: ("不支持的鉴权方式: {authStyle}。可选: {supported}",),
    MODEL_AUTH_HEADER_REQUIRED: ("鉴权方式为 custom 时必须填写鉴权请求头名称",),
    MODEL_RESPONSE_NOT_JSON: ("模型未返回 JSON 对象",),
    TENANT_ID_REQUIRED: ("租户标识不能为空",),
    TENANT_ID_INVALID: ("租户标识不合法: {tenant}。只允许小写字母开头，字母、数字与下划线，最长 39 字符。",),
    QUOTA_RESOURCE_UNKNOWN: ("未知配额资源 {resource}，支持: {supported}",),
    QUOTA_LIMIT_NEGATIVE: ("配额上限不能为负数: {limit}",),
    CROSS_TENANT_ACCESS: ("检测到跨租户数据访问：期望 {expected}，实际 {actual}。已阻止该操作。",),
    SSO_GROUP_REQUIRED: ("提供方组名不能为空",),
    SSO_ROLE_UNKNOWN: ("未知平台角色 {roleCode}，可选: {supported}",),
    SSO_MAPPING_MISSING: ("组映射不存在: {providerGroup}",),
    SSO_IDENTITY_UNMAPPED: (
        "身份 {subject} 的组未映射到任何平台角色，已拒绝。"
        "请由平台管理员声明组到角色的映射——未映射即无权限，不会给默认角色。",
    ),
    SSO_NOT_ENABLED: ("SSO 未启用，缺少配置: {missing}",),
    SSO_ALGORITHM_UNSUPPORTED: ("不支持的签名算法 {algorithm}，可选: {supported}",),
    SSO_ASSERTION_EXPIRED: ("断言已过期",),
    SSO_ASSERTION_NO_EXPIRY: ("断言缺少 exp，不接受永不过期的凭据",),
    SSO_ASSERTION_MALFORMED: ("断言格式无效：应为三段 JWT",),
    SSO_SIGNATURE_INVALID: ("断言签名校验失败",),
    SSO_ISSUER_MISMATCH: ("签发方不匹配: {issuer}",),
    SSO_AUDIENCE_MISMATCH: ("受众不匹配: {audience}",),
    UNSUPPORTED_STATUS: ("不支持的状态: {status}",),
    RULE_FUNCTION_NOT_ALLOWED: ("只允许 {allowed} 函数",),
    MIGRATION_FAILED: ("迁移 {version}（{description}）失败，后续迁移未执行: {reason}",),
    SCAFFOLD_PROJECT_NAME_INVALID: (
        "项目名 {name} 不合法：需为小写字母开头、2-40 位的小写字母／数字／下划线（它会成为 Python 包名）",
    ),
    SCAFFOLD_FILES_EXIST: ("以下文件已存在，未做任何修改: {files}。生成到新目录再对比合并——脚手架不覆盖既有代码。",),
    SCAFFOLD_EXTENSION_UNKNOWN: ("未知扩展点 {extension}，可选: {supported}",),
    QUESTION_REQUIRED: ("问题不能为空",),
    FILE_NAME_REQUIRED: ("文件名不能为空",),
    FILE_CONTENT_EMPTY: ("文件内容为空",),
}


def _compile(template: str) -> tuple[re.Pattern[str], tuple[str, ...]]:
    """A template as a regex plus the fact names in the order they appear.

    Built by escaping the literal parts and inserting a capturing group for each `{name}`,
    anchored at both ends. Anchoring matters more than it looks: an unanchored pattern for
    `本体不存在` would also match `本体不存在: 1`, and whichever was tried first would
    decide the facts -- so `identify` tries the exact templates before the parameterised
    ones and relies on this to keep them apart.
    """
    names = tuple(re.findall(r"\{(\w+)\}", template))
    parts = re.split(r"\{\w+\}", template)
    pattern = "^" + "(.*?)".join(re.escape(part) for part in parts) + "$"
    return re.compile(pattern, re.DOTALL), names


_EXACT: dict[str, str] = {}
_PATTERNS: list[tuple[str, re.Pattern[str], tuple[str, ...]]] = []

for _code, _templates in TEMPLATES.items():
    for _template in _templates:
        if "{" in _template:
            _pattern, _names = _compile(_template)
            _PATTERNS.append((_code, _pattern, _names))
        else:
            _EXACT[_template] = _code

# Longest literal first, so a template that begins with another template's text is tried
# before the shorter one it would otherwise be mistaken for.
_PATTERNS.sort(key=lambda entry: max(len(part) for part in entry[1].pattern.split("(.*?)")), reverse=True)


def identify(sentence: str) -> tuple[str, dict[str, str]]:
    """The code and facts for one of this platform's own refusals, or `("", {})`.

    An unidentified sentence keeps the empty code on purpose. The console then shows the
    sentence the server wrote, which is still true and still readable -- the failure mode of
    guessing here would be a wrong translation attached to a right message.
    """
    if not sentence:
        return "", {}
    exact = _EXACT.get(sentence)
    if exact:
        return exact, {}
    for code, pattern, names in _PATTERNS:
        match = pattern.match(sentence)
        if match:
            return code, dict(zip(names, match.groups(), strict=True))
    return "", {}


def sentence_for(code: str, **facts: Any) -> str:
    """The platform's own sentence for a code, with its facts filled in.

    For tests and for callers that need the sentence a console would have been given. Raises
    on a code that is not registered: a misspelled code here is a typo in a registry entry,
    not a runtime condition, and `tests/test_error_codes.py` exercises every code through
    this function so a template with a fact nobody supplies cannot ship.
    """
    templates = TEMPLATES.get(code)
    if not templates:
        raise KeyError(f"未注册的错误码: {code}")
    return templates[0].format(**facts)


def decorate(detail: Any) -> dict[str, Any]:
    """The response body for a refused request, with a code when the sentence has one.

    `detail` is passed through untouched whatever happens to it: FastAPI allows a structured
    detail, the console reads it, and a refusal nobody has named yet must not start rendering
    differently just because it has no code.
    """
    body: dict[str, Any] = {"detail": detail}
    if not isinstance(detail, str):
        return body
    code, facts = identify(detail)
    if code:
        body["code"] = code
        if facts:
            body["facts"] = facts
    return body
