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
| R4-N1 | 安装器：普通文件占据所需目录位置，--force 下仍部分写入后 rc1 | 自测 PASS | a887cd9；预检判为冲突 rc2、零写入（含 --force）；待 R5 复核 |
| R4-N2 | vb_init `_compensate` 无归属判据，项目内 Junction 重定向导致误删 | 自测 PASS | 9c91a9e；仅当前内容==本进程写入值才还原/删除，否则记残留；新建目录登记 baseline 并在父路径校验；回滚跳过项一律进残留，不再宣称“已回滚” |
| R4-N3 | 安装器：内层链接分量 rc2（文档写 rc1） | 自测 PASS | a887cd9；平凡的退出码对齐：链接/越界 → REFUSED rc1；测试断言收紧为 rc==1 |
| R4-N4 | 安装器：dest 上层分量为 Junction 时跟随写出项目外 | OPEN | 见 R4-REPORT |
| R4-N5 | 安装器：未检查 dest 与 source 重叠 | OPEN | 见 R4-REPORT |
| R4-N6 | vb_init `--json` 包装层按字面匹配 argv（缩写/等号写法） | OPEN | 见 R4-REPORT |
| R4-N7 | `--standard` / VB_STANDARD_HOME 可指向任意自校验目录 | OPEN | 既有；见 R4-REPORT |
| R4-N8 | c08407d 残留报告描述不准确 | OPEN | R4-N2 修复顺带让未回滚项进残留，但描述准确性未逐项复核，仍 OPEN |
| R4-N9 | 项目位于盘符根目录时写入全被拒 | OPEN | Info |
| R4-N10 | 测试与清单的小缺口（清单中 ../、绝对路径键被保留等） | OPEN | Info |
| R4-c08407d | 对 c08407d（及本分支）的独立复核 | 已完成 R4 | R4-REPORT.md：PASS-with-findings；R5 复核 5327eb9..HEAD 待安排 |
| VENDOR-SCOPE | vendor 范围决策（全量 vendored 还是精简） | OPEN | 需 Chris 决定 |
| POC-PUSH | poc/vibecoding-skill-v0.1.0 与本 fix 分支均未推送远程 | OPEN | 推送需 Chris 明确批准 |
