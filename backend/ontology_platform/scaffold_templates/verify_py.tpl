"""对本项目的扩展实现跑平台的一致性契约。

契约随 `aletheia-onto` 发布，不需要 clone 平台仓库、也不需要 pytest——
要求装测试框架才能验证插件，对最需要这个检查的集成方恰好是道门槛。

失败时退出码非 0，可直接作 CI 门禁。
"""

from __future__ import annotations

from ontology_platform.conformance import describe_suites

from {{package}} import setup

# 本项目注册的扩展中，有可执行契约的：
{{covered}}


def main() -> int:
    setup()
    print("平台提供的契约:")
    for suite in describe_suites():
        print(f"  {suite['suite']:24} {suite.get('extensionPoint', '')}")
    print()
    print("对你的实现调用对应的 check_*()，并让不合规时返回非 0。例如：")
    print("    from ontology_platform.conformance import check_embedding_model")
    print("    report = check_embedding_model(my_model, subject='my_model')")
    print("    print(report.summary())")
    print("    return 0 if report.conformant else 1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
