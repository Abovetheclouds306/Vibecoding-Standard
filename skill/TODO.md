# TODO（skill/ 任务真相源）

状态取值：PASS（开发者自测）/ FAIL / UNKNOWN / NOT_RUN / OPEN。自测 PASS 不等于 R4 复核通过。

| ID | 事项 | 状态 | 说明 |
|---|---|---|---|
| INS-1 | install_skill.py `--force` 会 rmtree 删除未知内容 | 自测 PASS | 95d41bf；归属清单 + 冲突拒绝 + 链接/边界；待 R4 |
| CLI-1 | `--json` 失败路径输出契约 JSON（status/error/rc） | 自测 PASS | 60a4ed1 |
| CLI-2 | `--update-block` 状态与 rc 一致 | 自测 PASS | 原实现已正确，补测试；JSON 增加 status |
| CLI-3 | assets/AGENTS.block.md 与 BLOCK 渲染防漂移 | 自测 PASS | 原实现一致，补测试 |
| CLI-4 | vendor 定位与项目搬迁 | 自测 PASS | 原实现正确，补测试 |
| CLI-5 | 技能缺失如实报告 | 自测 PASS | 修复：显式 `--standard` 无效时原先静默回退到其他副本 |
| CLI-6 | init / 安装器幂等 | 自测 PASS | 补测试 |
| LNK-F | 文件级符号链接用例 | NOT_RUN | 本机无创建文件符号链接权限（需开发者模式/管理员）；目录 Junction 用例已运行 |
| R4-c08407d | 对 c08407d（及本分支）的独立复核 | OPEN | 尚无 R4；R1–R3 只有原始日志无结论文档 |
| VENDOR-SCOPE | vendor 范围决策（全量 vendored 还是精简） | OPEN | 需 Chris 决定 |
| POC-PUSH | poc/vibecoding-skill-v0.1.0 与本 fix 分支均未推送远程 | OPEN | 推送需 Chris 明确批准 |
