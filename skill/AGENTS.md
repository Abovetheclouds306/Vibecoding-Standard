# skill/ 开发入口规则（Vibecoding Skill）

本文件只是入口与指针，**不是第二份规范**。

- 权威规范：`skill/vibecoding/vendor/vibecoding-standard/`（vendored v1.2.7，来源与哈希见该目录 `VENDORED.md`）。冲突时以 vendor 为准。
- vendor 目录只读：禁止修改 `skill/vibecoding/vendor/**`；改动后必须 `python tools/verify_manifest.py`（cwd=vendor 目录）PASS。
- 任务真相源：`skill/TODO.md`（待办与状态）、`skill/HANDOFF.md`（最近一轮交接与证据）。本地 Git 状态是唯一事实。
- 测试：`python -m unittest discover -s skill/tests -v`（仓库根目录）；测试只能用系统临时目录，禁止触碰真实技能安装目录。
- 开发者自测 ≠ 独立复核（R4）。结论标 PASS / FAIL / UNKNOWN / NOT_RUN。
- 禁止：push / merge / tag / release、reset / clean、弱化断言、新增功能或改变规范契约。
