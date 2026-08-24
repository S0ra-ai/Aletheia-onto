# 复制为 .env 并填入真实值。.env 已在 .gitignore 中。
#
# 本文件**不包含任何可用默认值**：一个能直接用的示例口令，就是一个会被直接用的口令。

# 引导管理员口令。不设则首次 init 生成随机口令并只打印一次。
ONTOLOGY_ADMIN_PASSWORD=

# 平台库位置。默认 ~/.{{package}}/platform.sqlite3
{{UPPER}}_PLATFORM_DB=

# CORS 允许来源，逗号分隔。**不要用 `*`**：通配会让任意站点携用户凭据驱动本 API，
# 部署前自检会因此阻断。
ONTOLOGY_ALLOWED_ORIGINS=http://127.0.0.1:3000

# 传统系统连接串。名称需与 config.py 的 DATA_SOURCES 一致。
# {{UPPER}}_CONTRACT_URI=postgresql://user:password@host:5432/contracts

# 模型服务（可选）。未配置时平台回退本地启发式，功能不中断。
OPENROUTER_API_KEY=

# SSO（可选）。三项需全部设置才启用；半配置状态按「SSO 关闭」处理，
# 而非「SSO 开启且接受任意断言」。
ONTOLOGY_SSO_ISSUER=
ONTOLOGY_SSO_AUDIENCE=
ONTOLOGY_SSO_SECRET=
