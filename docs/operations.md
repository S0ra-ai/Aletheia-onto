# 运维手册

## 日常监控

### 健康检查
```bash
# 检查服务状态
curl http://localhost:8000/health

# 检查指标
curl http://localhost:8000/metrics
```

### 日志查看

日志默认写 stderr，容器化部署交给运行时收集（`docker logs`／Kubernetes）。需要落盘时
设置 `ONTOLOGY_LOG_FILE`，目录会自动创建，按 10 MiB 轮转、保留 5 份：

```bash
export ONTOLOGY_LOG_FILE=/var/log/aletheia/platform.log
```

要交给日志聚合系统解析时启用 JSON（每行一个对象）：

```bash
export ONTOLOGY_LOG_FORMAT=json     # 默认 text，给人看
export ONTOLOGY_LOG_LEVEL=INFO      # 默认 INFO
```

两种格式都带 `request_id`：文本格式是行内的 `request_id=…`，JSON 格式是
`requestId` 字段。**每一条日志（包括依赖库内部发出的告警）都带当前请求的 id**，
因为 id 在请求进入时绑定到上下文，而不是由各调用点自行传递。

按请求追日志：

```bash
grep "request_id=a1b2c3…" /var/log/aletheia/platform.log
```

id 的来源有两个：平台生成（full UUID4），或调用方通过 `X-Request-Id` 头传入——
网关可以借此把自己的 id 与本服务的日志对上。响应里始终回带同一个 id。

**排查 500 时先从响应体拿 id。** 未处理异常的响应是
`{"detail": …, "code": "internal_error", "requestId": "…"}`，异常本身只进日志、不进响应体
（异常文本含文件路径、SQL 片段，偶尔还有数据行）。用户报障时把这个 id 贴过来即可定位。

> 请求日志只记录路径，**不记录查询串**：查询串常带 `?token=` 之类的凭据，而访问日志
> 最常被送到第三方聚合平台。uvicorn 自带的访问日志会把整行请求（含查询串）打出来，
> 因此启动时已将其级别压到 WARNING——只保留一份访问日志，且是不泄露参数的那一份。

### 请求限流

默认**不启用**，因为合适的额度取决于部署的流量，这个数字包本身无法知道。
启用后按调用方地址计数，并**在认证之前生效**——未认证的洪泛正是要限制的对象：

```bash
export ONTOLOGY_RATE_LIMIT_PER_MINUTE=600        # 0 或未设置 = 不限制
export ONTOLOGY_RATE_LIMIT_AUTH_PER_MINUTE=10    # 登录／SSO，默认 10，更严
```

被拒的请求返回 `429` 且带标准 `Retry-After` 头；正常响应带 `X-RateLimit-Limit` 与
`X-RateLimit-Remaining`。健康检查与 `/metrics` 等公开路径不计数，
否则监控会消耗掉它自己所在地址的额度。

计数器按进程独立：多 worker 部署下实际额度是配置值乘以 worker 数。跨进程共享计数需要
本包不依赖的存储，这一点写在[已知限制](limitations.zh-CN.md)里而不是被掩盖。

`aletheia preflight` 会对「可从网络访问但未设限流」给出 warning。

### 指标监控
访问 Prometheus: http://localhost:9090
- HTTP 请求速率
- 错误率
- 响应时间 P99
- 活跃会话数

## 备份与恢复

### 创建备份

内置 HTTP 备份只支持 SQLite 平台库，且 `/admin/backup/*` 要求管理员令牌：
```bash
curl -X POST http://localhost:8000/admin/backup/create \
  -H "Authorization: Bearer $ONTOLOGY_ADMIN_TOKEN"
```

### 列出备份
```bash
curl http://localhost:8000/admin/backup/list \
  -H "Authorization: Bearer $ONTOLOGY_ADMIN_TOKEN"
```

### 恢复备份
```bash
curl -X POST http://localhost:8000/admin/backup/restore/{backup_name} \
  -H "Authorization: Bearer $ONTOLOGY_ADMIN_TOKEN"
```

恢复会替换当前 SQLite 平台库，应在停止服务后执行。**恢复前平台会自动把当前库另存为
一份 `before-restore-<UTC 时间戳>` 备份**，并在响应里用 `safetyCopy` 报出它的名字——
备份列表里几十个名字相近的归档，选错一个是很平常的事，而换错的那一次必须能换回来。
快照生成失败时**恢复会被拒绝**（fail-closed）：先弄丢现在这一份、再换上一份可能不对的，
比不做这次恢复更糟。

生产参考编排使用 PostgreSQL，
数据库备份请使用 `pg_dump`／PITR；内置备份接口会显式拒绝服务端数据库，
而不是生成不可恢复的物理快照。

## 故障排查

### 服务无法启动
1. `aletheia preflight` —— 部署前自检会指出具体是哪个配置项不通。
   非本机监听时 `aletheia serve` 自己也会先跑一遍，不通过就拒绝启动。
2. 检查端口占用: `lsof -i :8000`
3. 检查平台库: `ls -la data/platform.sqlite3`

### 500 错误
1. 从响应体取 `requestId`。
2. `grep "request_id=<该值>" <日志文件>`，拿到完整堆栈与该请求的全部日志行。
3. 若日志在 stderr，容器部署用 `docker logs <容器> 2>&1 | grep <该值>`。

### 性能问题
1. 查看 `/metrics`：请求速率、错误率、响应时间。
2. 检查数据库连接数——平台不使用连接池，每个 `connect()` 新建连接，
   连接数随并发线性上升。
3. 检查内存使用: `top -p $(pgrep -f uvicorn)`

### 认证问题
1. 重置管理员密码（`aletheia` 提供的管理员引导流程）。
2. 清除过期会话——服务启动时会自动清理，日志中有清理条数。
3. 认证走**不透明 Bearer 令牌**（库中只存摘要），不是 JWT；
   JWT 只出现在 SSO 那条路径上（见[配置](configuration.zh-CN.md)）。

## 升级步骤

1. 备份数据库（`aletheia` 的备份接口或 `pg_dump`）。
2. 停止服务。
3. `pip install -U aletheia-onto`。
4. 启动服务——**迁移在启动时自动应用**，没有单独的手工迁移步骤；
   已应用的版本会记入日志，并记录在平台库的版本账本中。
5. 验证健康：`curl http://localhost:8000/health`。

## 安全清单

- [ ] 修改默认管理员密码
- [ ] 配置 HTTPS
- [ ] 设置防火墙规则
- [ ] 启用日志审计（`ONTOLOGY_LOG_FILE`，或交给日志聚合）
- [ ] 设置请求限流（`ONTOLOGY_RATE_LIMIT_PER_MINUTE`）
- [ ] 配置备份计划
- [ ] 设置监控告警
