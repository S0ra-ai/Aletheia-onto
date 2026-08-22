# 接入自定义模型服务

平台使用 **OpenAI 兼容的 `chat/completions` 协议**，因此任何实现该协议的服务都可接入：
官方 API、中转站与自定义订阅、自建 vLLM / Ollama、Azure OpenAI、国内厂商的兼容端点。

> 未配置 API Key 时，问答与建模会**回退本地启发式**，功能不中断——
> 平台不会因为缺少模型而不可用。

## 为什么只配 Base URL 不够

各服务商在两件事上并不一致，而这两件事都会让请求直接失败：

| 差异 | 症状 |
|---|---|
| 密钥的传递方式 | `401`：Azure 用 `api-key` 请求头，不是 `Authorization: Bearer` |
| 能否容忍额外字段 | `400`：`service_tier`／`session_id` 是 OpenRouter 扩展，严格的兼容实现（vLLM、LM Studio、部分中转站）遇到未知字段直接拒绝 |
| Base URL 的路径形态 | `404`：有的网关给的已是完整 `/chat/completions`，Azure 还带 `?api-version=` |

因此除 Base URL 外还有三项兼容性设置。

## 快速预设

模型配置页右上角可一键套用：

| 预设 | Base URL | 鉴权方式 | 扩展字段 |
|---|---|:--:|:--:|
| OpenRouter | `https://openrouter.ai/api/v1` | bearer | 开 |
| OpenAI 官方 | `https://api.openai.com/v1` | bearer | 关 |
| 中转站／自定义订阅 | `https://<你的域名>/v1` | bearer | 关 |
| Azure OpenAI | `https://<资源>.openai.azure.com/openai/deployments/<部署>/chat/completions?api-version=2024-02-01` | api-key | 关 |
| 自建 vLLM / Ollama | `http://127.0.0.1:8000/v1` | none | 关 |
| 阿里云百炼 / 通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | bearer | 关 |

套用预设后需自行补齐密钥与模型名。

## 配置项说明

### 鉴权方式

| 取值 | 发送形式 | 适用 |
|---|---|---|
| `bearer` | `Authorization: Bearer <key>` | 绝大多数服务 |
| `api-key` | `api-key: <key>` | Azure OpenAI |
| `custom` | `<自定义头>: <key>` | 需要特殊头名的网关 |
| `none` | 不发送密钥 | 内网自建服务 |

选 `custom` 时必须填写请求头名称，否则保存会被拒绝——
静默丢弃密钥比报错更难排查。

### 发送 OpenRouter 扩展字段

控制是否在请求体中带 `service_tier` 与 `session_id`。
**接入非 OpenRouter 服务时建议关闭。**

### 附加请求头

JSON 对象，例如 `{"X-Tenant-Id": "acme"}`。
此处的键会**覆盖**自动生成的同名请求头，可作为最后的逃生舱。

### Base URL 的路径处理

平台按以下规则决定实际调用地址：

- 通常在 Base URL 后追加 `/chat/completions`
- 若 Base URL 中**已包含** `/chat/completions`，则原样使用，不重复拼接
- 查询串（如 Azure 的 `?api-version=`）会被保留

配置页会显示**实际会被调用的完整地址**，保存前即可核对。

## 环境变量

不使用界面配置时，可通过环境变量提供（数据库中的配置优先级更高）：

| 变量 | 作用 |
|---|---|
| `OPENROUTER_API_KEY` | API 密钥 |
| `OPENROUTER_BASE_URL` | Base URL |
| `OPENROUTER_MODEL` | 模型名 |
| `ONTOLOGY_MODEL_AUTH_STYLE` | 鉴权方式 |
| `ONTOLOGY_MODEL_AUTH_HEADER` | 自定义鉴权头名称 |
| `ONTOLOGY_MODEL_EXTRA_HEADERS` | 附加请求头（JSON 字符串） |
| `ONTOLOGY_MODEL_SEND_EXTRAS` | 设为 `0` 关闭扩展字段 |

## 排错

| 现象 | 优先检查 |
|---|---|
| `401` | 鉴权方式是否匹配；密钥是否已过期 |
| `400` 且提示未知字段 | 关闭「发送 OpenRouter 扩展字段」 |
| `404` | Base URL 路径；对照配置页显示的实际地址 |
| 连接超时 | 自建服务的地址与端口；适当增大超时 |
| 返回内容为空 | 模型名是否为该服务商的合法标识（Azure 应填部署名） |

配置页的「测试连接」会返回具体错误，并按状态码提示最可能的成因。

## 安全

- API Key 在接口响应中**只返回首尾字符**，不会回显完整值
- 配置页留空密钥表示「保持现有密钥不变」，而非清空
- 附加请求头中的值同样会进入请求，请勿在其中放入无关凭据
