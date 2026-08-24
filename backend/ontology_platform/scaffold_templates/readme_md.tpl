# {{package}}

基于 [Aletheia](https://github.com/S0ra-ai/Aletheia-onto) 的业务语义内核部署。

**本项目不是 fork。** 平台以依赖形式安装，升级即 `pip install -U aletheia-onto`，
本项目无需改动——生成的代码只调用公开入口。

## 启动

```bash
cp .env.example .env      # 填入真实值
pip install -e .
python -m {{package}} init      # 建库 + 引导管理员（口令只打印一次）
python -m {{package}} serve     # 非本机监听时会强制部署前自检
```

用 `python -m {{package}}` 而非 `aletheia`：后者**不会**加载本项目注册的扩展。

## 接入你的系统

```bash
python -m {{package}} connect postgresql://user:pass@host/db --domain {{domain}}
python -m {{package}} model 1                  # 生成本体草案
python -m {{package}} assess 1 contract 1      # 对一个实例产出判定
```

连接串放 `.env`，并在 `config.py` 的 `DATA_SOURCES` 中登记**环境变量名**——
那样 `config.py` 可以提交，而凭据不会。

## 本项目的扩展

{{extension_list}}

`python verify.py` 对这些实现跑平台的一致性契约。

## 上生产前

```bash
python -m {{package}} preflight
```

拦的是静默失败：`ONTOLOGY_AUTH_DISABLED` 残留会让整套 API 免鉴权暴露、
CORS 通配会让任意站点驱动本 API、SQLite 配多工作进程会表现为间歇性超时。
存在阻断项时退出码非 0，可直接作 CI 门禁。

## 审计与导出

```bash
python -m {{package}} audit --start 2026-08-01 --end 2026-09-01
python -m {{package}} export 1 --format owl > ontology.ttl
```

`audit` 报出本期从未触发的已发布规则、覆盖了发布门禁的发布、以及判定的留痕完整率；
存在阻断级发现时退出码非 0。`export` 输出 OWL／SHACL／JSON-LD／Turtle。
