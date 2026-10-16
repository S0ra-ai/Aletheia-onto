/**
 * model —— 页面：pages/model/ModelConfig.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('model.…')`。
 */
import type { MessageEntry } from './shell';

export const model: Record<string, MessageEntry> = {
  'title': { zh: '模型配置', en: 'Model configuration' },
  'intro': {
    zh: '平台使用 OpenAI 兼容的 chat/completions 协议，因此任何实现该协议的服务都可接入：官方 API、中转站与自定义订阅、自建 vLLM / Ollama、Azure OpenAI、国内厂商兼容端点。',
    en: 'The platform speaks the OpenAI-compatible chat/completions protocol, so any service that implements it can be connected: official APIs, relays and custom subscriptions, self-hosted vLLM / Ollama, Azure OpenAI, and compatible endpoints from Chinese providers.',
  },
  'introHint': {
    zh: '未配置密钥时，问答与建模会回退到本地启发式，功能不中断。DeepSeek 官方 API 可通过下方预设直接接入。',
    en: 'Without a configured key, question answering and modelling fall back to local heuristics and keep working. The official DeepSeek API can be connected directly through the preset below.',
  },

  'configStatus': { zh: '配置状态', en: 'Configuration status' },
  'configured': { zh: '已配置', en: 'Configured' },
  'notConfigured': { zh: '未配置', en: 'Not configured' },
  'currentModel': { zh: '当前模型', en: 'Current model' },
  'notSet': { zh: '未设置', en: 'Not set' },
  'authStyleLabel': { zh: '鉴权方式', en: 'Authentication' },
  'resolvedEndpoint': { zh: '实际调用地址', en: 'Endpoint actually called' },

  'loadFailed': { zh: '获取配置失败', en: 'Could not load the configuration' },
  'saved': { zh: '配置保存成功', en: 'Configuration saved' },
  'saveFailed': { zh: '保存失败', en: 'Could not save the configuration' },
  'resetDone': { zh: '配置已重置', en: 'Configuration reset' },
  'resetFailed': { zh: '重置失败', en: 'Could not reset the configuration' },
  'testSucceeded': { zh: '连接测试成功', en: 'Connection test succeeded' },
  'testFailed': { zh: '测试失败', en: 'The connection test failed' },
  'presetApplied': { zh: '已套用「{name}」预设，请补齐密钥后保存', en: 'Applied the {name} preset. Add the key, then save.' },
  'extraHeadersNotObject': { zh: '附加请求头必须是 JSON 对象', en: 'Extra request headers must be a JSON object' },
  'extraHeadersInvalidJson': { zh: '附加请求头不是合法 JSON', en: 'Extra request headers are not valid JSON' },

  'preset.openrouter': { zh: 'OpenRouter', en: 'OpenRouter' },
  'preset.openai': { zh: 'OpenAI 官方', en: 'Official OpenAI' },
  'preset.relay': { zh: '中转站 / 自定义订阅', en: 'Relay / custom subscription' },
  'preset.azure': { zh: 'Azure OpenAI', en: 'Azure OpenAI' },
  'preset.vllm': { zh: '自建 vLLM / Ollama', en: 'Self-hosted vLLM / Ollama' },
  'preset.dashscope': { zh: '阿里云百炼 / 通义', en: 'Alibaba Cloud DashScope / Qwen' },
  'preset.deepseek': { zh: 'DeepSeek 官方 API', en: 'DeepSeek official API' },

  'authStyle.bearer': { zh: 'Bearer Token（多数服务）', en: 'Bearer token (most services)' },
  'authStyle.apiKey': { zh: 'api-key 请求头（Azure）', en: 'api-key header (Azure)' },
  'authStyle.custom': { zh: '自定义请求头', en: 'Custom header' },
  'authStyle.none': { zh: '不发送密钥（本地服务）', en: 'Send no key (local services)' },

  'connectionCard': { zh: '接入配置', en: 'Connection settings' },
  'presets': { zh: '快速预设', en: 'Presets' },
  'providerPlaceholder': { zh: '选择服务商', en: 'Choose a provider' },
  'providerLabel': { zh: '服务商标识', en: 'Provider identifier' },
  'baseUrlRequired': { zh: '请输入 API 地址', en: 'Enter the API base URL' },
  'baseUrlHint': {
    zh: '通常以 /v1 结尾。若你的网关直接提供完整的 /chat/completions 地址（如 Azure），可整段填入，平台不会重复拼接。',
    en: 'Usually ends in /v1. If your gateway serves the full /chat/completions path directly, as Azure does, paste it whole and the platform will not append anything.',
  },
  'modelNameLabel': { zh: '模型名称', en: 'Model name' },
  'modelNameRequired': { zh: '请输入模型名称', en: 'Enter the model name' },
  'modelNameHint': { zh: '填写你的服务商所使用的模型标识；Azure 填部署名。', en: 'The model identifier your provider expects; for Azure, the deployment name.' },
  'apiKeyKeepHint': { zh: '留空则保持现有 Key 不变', en: 'Leave blank to keep the existing key' },
  'apiKeyLocalHint': { zh: '本地服务若无需鉴权，可将鉴权方式设为「不发送密钥」', en: 'If a local service needs no authentication, set the authentication method to "Send no key"' },
  'compatibility': { zh: '兼容性设置', en: 'Compatibility settings' },
  'authStyleHint': { zh: '不同服务商传递密钥的方式不同，选错会得到 401。', en: 'Providers pass the key in different ways; choosing the wrong one returns a 401.' },
  'authHeaderLabel': { zh: '自定义鉴权请求头名称', en: 'Custom authentication header name' },
  'authHeaderRequired': { zh: '请填写请求头名称', en: 'Enter the header name' },
  'authHeaderHint': { zh: '密钥将以该请求头原样发送，例如 X-Api-Token。', en: 'The key is sent verbatim in this header, for example X-Api-Token.' },
  'extrasTooltip': {
    zh: 'service_tier 与 session_id 是 OpenRouter 扩展字段。严格的 OpenAI 兼容服务（vLLM、LM Studio、部分中转站）会因未知字段直接返回 400。',
    en: 'service_tier and session_id are OpenRouter extension fields. Strict OpenAI-compatible services (vLLM, LM Studio, some relays) reject unknown fields with a 400.',
  },
  'extrasLabel': { zh: '发送 OpenRouter 扩展字段', en: 'Send OpenRouter extension fields' },
  'extrasHint': { zh: '接入非 OpenRouter 服务且遇到 400 错误时，请关闭此项。', en: 'Turn this off when connecting to a non-OpenRouter service and hitting 400 errors.' },
  'extraHeadersLabel': { zh: '附加请求头（可选，JSON）', en: 'Extra request headers (optional, JSON)' },
  'extraHeadersHint': {
    zh: '部分网关需要额外标识，例如 {"X-Tenant-Id": "acme"}。此处的键会覆盖上面自动生成的同名请求头。',
    en: 'Some gateways need extra markers, for example {"X-Tenant-Id": "acme"}. Keys entered here override the same-named headers generated above.',
  },
  'other': { zh: '其他', en: 'Other' },
  'serviceTierLabel': { zh: '服务层级', en: 'Service tier' },
  'serviceTierHint': { zh: '仅 OpenRouter', en: 'OpenRouter only' },
  'timeoutLabel': { zh: '超时（秒）', en: 'Timeout (seconds)' },
  'appTitleLabel': { zh: '应用标题', en: 'Application title' },
  'appTitleHint': { zh: '作为 X-Title 发送', en: 'Sent as X-Title' },
  'httpRefererHint': { zh: '可选，用于服务商归因', en: 'Optional; used for provider attribution' },
  'saveButton': { zh: '保存配置', en: 'Save configuration' },
  'testButton': { zh: '测试连接', en: 'Test connection' },
  'resetButton': { zh: '重置为默认', en: 'Reset to defaults' },

  'connected': { zh: '连接成功', en: 'Connected' },
  'connectionFailed': { zh: '连接失败', en: 'Connection failed' },
  'returnedModel': { zh: '返回模型：{model}', en: 'Model returned: {model}' },
  'testHint': {
    zh: '401 通常是鉴权方式不匹配；400 常见于未知字段，可尝试关闭「发送 OpenRouter 扩展字段」；404 多为 Base URL 路径不正确。',
    en: 'A 401 usually means the authentication method does not match; a 400 is often an unknown field, so try turning off "Send OpenRouter extension fields"; a 404 usually means the Base URL path is wrong.',
  },
};
