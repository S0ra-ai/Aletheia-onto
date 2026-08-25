# 配置

> 全部环境变量：运行与安全、平台库、SSO、阈值与命名。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

可配置项集中在 [`backend/ontology_platform/config.py`](../backend/ontology_platform/config.py)，
全部可由环境变量覆盖。

## 运行与安全

| 变量 | 作用 | 默认 |
|---|---|---|
| `ONTOLOGY_ADMIN_USERNAME` | 引导管理员用户名 | `admin` |
| `ONTOLOGY_ADMIN_PASSWORD` | 引导管理员口令 | 未设则生成随机口令并打印 |
| `ONTOLOGY_SESSION_TTL_HOURS` | 会话有效期（小时） | `12` |
| `ONTOLOGY_AUTH_DISABLED` | 设为 `1` 关闭全部认证，**仅限本地开发** | 未设（认证开启） |
| `ONTOLOGY_ALLOWED_ORIGINS` | CORS 允许来源，逗号分隔 | `http://127.0.0.1:3000,http://localhost:3000` |

## SSO（单点登录）

三项全部设置后 SSO 才启用——半配置状态按「SSO 关闭」处理，而非「SSO 开启且接受任意断言」。

| 变量 | 作用 | 默认 |
|---|---|---|
| `ONTOLOGY_SSO_ISSUER` | 期望的 `iss`，不匹配即拒绝 | 未设（SSO 关闭） |
| `ONTOLOGY_SSO_AUDIENCE` | 期望的 `aud`，防止其他服务的令牌在此复用 | 未设（SSO 关闭） |
| `ONTOLOGY_SSO_SECRET` | 签名校验密钥。放环境变量而非库里——库里的凭据等于每份备份里的凭据 | 未设（SSO 关闭） |
| `ONTOLOGY_SSO_ALGORITHM` | `HS256`／`HS384`／`HS512`。**算法取自配置，绝不取自令牌头** | `HS256` |
| `ONTOLOGY_SSO_GROUP_CLAIM` | 承载组的声明名 | `groups` |
| `ONTOLOGY_SSO_USERNAME_CLAIM` | 承载用户标识的声明名 | `sub` |

**身份由提供方断言，权限由平台决定。** OIDC 令牌可以带任何声明，包括 `role: admin`——
信它就等于把授权边界搬进了别人的配置里。因此声明绝不直接变成权限：
由管理员声明「提供方组 → 平台角色」的映射，**未映射到任何角色的身份直接被拒绝**，
而不是给一个默认角色——默认角色看起来安全，实际会静默地把「读取平台可达的全部业务对象」
授予目录里的每一名员工。

本地账号并不被取代：提供方不可达时仍需要一条进得去的路，
而「IdP 挂了所以没人能修 IdP 集成」是真实存在的故障形态。

## 平台库

| 变量 | 作用 | 默认 |
|---|---|---|
| `ONTOLOGY_PLATFORM_DB_TYPE` | `sqlite`／`mysql`／`postgresql` | `sqlite` |
| `ONTOLOGY_PLATFORM_DB_URI` | 平台库连接串 | 本地 SQLite 文件 |
| `ONTOLOGY_PLATFORM_DB_FILE` | 直接指定 SQLite 平台库**文件**（优先于 `ONTOLOGY_DATA_DIR`） | 未设 |
| `ONTOLOGY_DATA_DIR` | 平台库所在**目录**，文件名固定为 `platform.sqlite3` | 源码树下为 `data/`，否则 `~/.aletheia` |
| `ONTOLOGY_PLATFORM_SQLITE_BUSY_TIMEOUT_MS` | SQLite busy_timeout | `5000` |

> **`serve` 与其他命令用同一个库。** `aletheia serve --platform-db X` 会把 `X`
> 传给被服务的进程，并在启动时打印实际使用的路径。
> 此前它做不到：`uvicorn` 在新进程里导入应用，只能从环境变量解析平台库，
> 于是 `serve --platform-db X` 服务的是**另一个**库——
> 而症状是 API 返回空本体列表，读起来像「我的数据没保存」，
> 于是排查会从重跑 `model`、怀疑写入开始，唯一不像的就是路径不一致。

## 阈值与命名

| 组 | 内容 | 环境变量前缀 |
|---|---|---|
| `QUERY_LIMITS` | 分页上限、一致性采样、枚举识别 distinct 上下界 | `ONTOLOGY_DEFAULT_PAGE_SIZE`、`ONTOLOGY_MAX_PAGE_SIZE`、`ONTOLOGY_ENUM_*` |
| `MAPPING_CONFIDENCE` | 映射候选置信度（蓝图／结构／词表／弱匹配） | `ONTOLOGY_CONFIDENCE_*` |
| `ANSWER_CONFIDENCE` | 问答置信度 | `ONTOLOGY_ANSWER_CONFIDENCE_*` |
| `RESOLUTION_CONFIDENCE` | 实例识别置信度与加成 | `ONTOLOGY_RESOLUTION_*` |
| `SEMANTIC_ASSET_NAMING` | JSON-LD／Turtle 的 IRI 命名空间 | `ONTOLOGY_VOCABULARY_BASE_IRI`、`ONTOLOGY_ASSET_BASE_IRI` |
| `MODEL_PROVIDER_DEFAULTS` | 模型端点、模型名、超时、service tier | `OPENROUTER_*` |

模型密钥 `OPENROUTER_API_KEY` 未配置时，问答与建模回退本地启发式，功能不中断。
