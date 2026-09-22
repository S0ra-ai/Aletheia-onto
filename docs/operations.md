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
```bash
# 查看应用日志
tail -f data/logs/platform.log

# 查看请求日志
grep "request_id" data/logs/platform.log
```

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

恢复会替换当前 SQLite 平台库，应在停止服务后执行。生产参考编排使用 PostgreSQL，
数据库备份请使用 `pg_dump`／PITR；内置备份接口会显式拒绝服务端数据库，
而不是生成不可恢复的物理快照。

## 故障排查

### 服务无法启动
1. 检查端口占用: `lsof -i :8000`
2. 检查数据库: `ls -la data/platform.sqlite3`
3. 查看日志: `tail -100 /tmp/backend.log`

### 性能问题
1. 检查数据库连接数
2. 查看慢查询日志
3. 检查内存使用: `top -p $(pgrep -f uvicorn)`

### 认证问题
1. 重置管理员密码
2. 清除过期会话
3. 检查 JWT 配置

## 升级步骤

1. 备份数据库
2. 停止服务
3. 更新代码
4. 运行迁移
5. 启动服务
6. 验证健康

## 安全清单

- [ ] 修改默认管理员密码
- [ ] 配置 HTTPS
- [ ] 设置防火墙规则
- [ ] 启用日志审计
- [ ] 配置备份计划
- [ ] 设置监控告警
