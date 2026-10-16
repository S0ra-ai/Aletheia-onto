# 私有化部署

> 两阶段镜像、参考编排，以及拦下静默误配的部署前自检。

返回 [中文 README](../README.zh-CN.md) · [English README](../README.md)

```bash
cp deploy/.env.example deploy/.env    # 填入真实值，范例里没有任何可用默认值
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d
```

镜像两阶段构建、非 root 运行、不内置任何凭据或预置数据库。
参考编排用 PostgreSQL 作平台库，数据库端口不映射到宿主。

## 定时备份

**`scripts/backup.sh` 只备份本地 SQLite 平台库。** 参考编排用的是 PostgreSQL，那种部署请用
`pg_dump`／PITR：脚本头部与 `backup.py` 都会拒绝服务端数据库，而不是生成一份无法恢复的物理快照。

SQLite 部署：脚本**不猜数据库位置**，两个变量都必须显式给出；cron 不会继承你 shell 里的 export，
所以它们要写进 crontab 那一行本身，否则脚本会在建任何东西之前退出（`set -e` 加变量必填）：
```bash
crontab -e
0 2 * * * ONTOLOGY_PLATFORM_DB_FILE=/srv/aletheia/platform.sqlite3 ONTOLOGY_BACKUP_DIR=/srv/aletheia/backups /path/to/scripts/backup.sh >> /var/log/aletheia-backup.log 2>&1
```

`PYTHON_BIN` 指定脚本用的解释器（默认 `python3`）：平台装在 virtualenv 里时把它指向那个解释器。
环境变量见[配置](configuration.zh-CN.md)；恢复的步骤与「恢复前快照」见[运维](operations.md)。

## 部署前自检

```bash
aletheia preflight --workers 4 --expect-origin https://ontology.example.com
```

阻断项存在时退出码为 1，可直接作流水线门禁。
`aletheia serve` 在监听非本机地址时**强制**跑一次自检并拒绝启动——
没人会记得单独跑一个命令，而唯一需要它的那次部署，
恰好就是 `ONTOLOGY_AUTH_DISABLED=1` 忘了删的那次。

自检拦的都是**静默失败**——平台会正常启动、正常服务、看起来健康：

| 误配置 | 实际发生什么 | 级别 |
|---|---|:--:|
| `ONTOLOGY_AUTH_DISABLED=1` 残留 | 整套 API 无需令牌即可访问，**包括对遗留系统的写回** | 阻断 |
| CORS 为 `*` | 任意站点都能携带用户凭据驱动本 API | 阻断 |
| 管理员口令为占位值或短于 12 位 | 有人选了它，并会以为之后改过 | 阻断 |
| SQLite 配多工作进程 | 写入串行化，高并发下表现为**间歇性超时**而非配置错误 | 阻断 |
| 平台库文件权限含 group/other | 该文件保存全部数据源连接串，等同凭据存储 | 阻断 |
| CORS 仍是 localhost | 真实前端被拦，随后有人会用 `*` 绕过 | 警告 |
| 未设管理员口令 | 随机口令只打印一次，容器日志轮转后没人能登录 | 警告 |
| 连接串内联口令 | 会出现在进程列表、容器 inspect 与崩溃日志里 | 警告 |
| 未配置请求限流 | 单个调用方可以无上限地产生请求；**没有任何日志记录「哪些请求没被限流」**，第一个征兆就是服务被打垮 | 警告 |

单节点 SQLite 评估部署是**合理**形态，因此单工作进程时不阻断——
拒绝它会让人索性跳过整个检查。

完整取舍见 [ADR-0017](adr/0017-deployment-preflight.md)。

## 上线之前

[生产环境检查清单](production-checklist.md) 是要逐条走的那份清单——基础设施、密钥、
以及那些值对评估环境安全、对生产环境不安全的设置。

这份清单此前**从任何地方都到不了**：一个没人链接的页面就是一个没人读的页面，
而这 79 行上线前检查一直躺在仓库里，没有读者。
