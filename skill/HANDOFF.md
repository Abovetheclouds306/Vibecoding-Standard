# HANDOFF — fix/skill-ins1-cli-v0.1.1（开发者自测，非 R4）

## 1. 目标与范围
- 基线：c08407d6a779124efff295cf4716400fbd7c6786（poc/vibecoding-skill-v0.1.0，未改动）。
- 工作树：`F:\DOSS_Project\_worktrees\Vibecoding-Skill-v0.1.0-fix`，分支 `fix/skill-ins1-cli-v0.1.1`（仅本地，未推送）。
- 范围：P0 INS-1（安装器 --force 删除未知内容）；P1 CLI 契约（--json 失败、--update-block rc、BLOCK 防漂移、vendor 搬迁、技能缺失如实、幂等）。
- 未改：`skill/vibecoding/vendor/**`、main、v1.2.7、POC 分支及其工作树。

## 2. 提交与改动文件
- 95d41bf40c184e69d63a3d8a3dc8642695eeed65 fix(installer): INS-1
  - skill/tools/install_skill.py、skill/tests/test_install_skill.py（新）
- 60a4ed1b06cdfdee79bd839adfbb11dfbbd35bdb fix(vb_init): --json 失败契约、显式 --standard 如实拒绝
  - skill/vibecoding/scripts/vb_init.py、skill/tests/test_vb_init_cli.py（新）
- 本文档提交：skill/AGENTS.md、skill/TODO.md、skill/HANDOFF.md（SHA 见 `git log`）

## 3. 行为变化
- 安装器：写 `.vibecoding-install.json`（每个归属文件的 sha256）。仅新建、或更新「在清单中且未被改动」的文件；**从不删除**（过期的旧归属文件保留并报告）。
  任何冲突（归属文件被改、无清单且内容不同、文件位置变成目录、清单损坏）→ rc2 且一个文件都不写，--force 也不例外；已存在且有差异但没给 --force → rc2。
  目标路径任一层是符号链接/Junction 或 realpath 越界 → rc1。写入/校验失败 → rc1 `FAILED`，只有成功才输出「安装完成」。
- vb_init：`--json` 下所有路径只输出一个 JSON 对象：成功带 `status: ok|needs_decision`；失败为 `status: refused|failed|usage_error`，含 `rc`（等于退出码）、`error`、`messages`、`steps: []`、`needs_decision: false`、`block_updated: false`。
  显式 `--standard` 无效时拒绝（rc1），不再静默回退到技能内置/环境变量副本。

## 4. 命令与退出码（Windows，Python 3.14.3，PYTHONDONTWRITEBYTECODE=1）
| 命令 | 时点 | 退出码 | 结果 |
|---|---|---|---|
| `python -m unittest discover -s skill/tests -v` | 改动前 | 0 | 51 tests OK |
| `python tools/verify_manifest.py`（cwd=vendor） | 改动前 | 0 | PASS 33/0/0/0 |
| 新测试 × 旧版（`git show c08407d:` 复制到 %TEMP%\vbfix_old，经 VB_INSTALLER_UNDER_TEST / VB_INIT_UNDER_TEST 指向） | 判别 | 1 | 27 运行，19 FAIL，1 skip，7 PASS |
| 新测试 × 新版 | 判别 | 0 | 27 运行，0 FAIL，1 skip |
| `python -m unittest discover -s skill/tests -v` | 改动后 | 0 | 78 tests OK（skipped=1） |
| `python tools/verify_manifest.py`（cwd=vendor） | 改动后 | 0 | PASS 33/0/0/0 |

判别细目：安装器 16 个用例，旧版 11 FAIL / 1 skip / 4 PASS（幂等、dry-run、真实技能安装、无 --force 拒绝——正向回归保护）；CLI 11 个用例，旧版 8 FAIL / 3 PASS（BLOCK 防漂移、项目搬迁、init 幂等——原实现已正确，记为补测试）。CLI 旧版 FAIL 中 --update-block 两例只因缺少新增的 status 字段，旧版 rc 本身正确。

## 5. 文件保护与残留/安全限制
- 测试全部在 `tempfile.mkdtemp`（%TEMP%\vbins-* / vbcli-*）中进行；清理前先拆链接，避免跟随 Junction 删到外部。
- 文件级符号链接用例 NOT_RUN：本机无权限创建（需开发者模式/管理员）。目录 Junction 用例已运行并 PASS。
- 安装器的检查—写入之间存在 TOCTOU 窗口（写前对每个文件再做一次 guard + os.replace，缩小但未消除）。
- 安装器不删除过期文件：升级后可能残留旧归属文件（已在输出中列出）。
- 半途失败时已写入的文件不回滚（输出 FAILED 并说明不是完整安装）。
- 判别副本留在 %TEMP%\vbfix_old，日志 %TEMP%\vbfix-before.log / vbfix-old-disc.log / vbfix-new-disc.log / vbfix-after.log。

## 6. 状态
- PASS（自测）：INS-1、CLI-1..6、vendor 校验、改动前后全套测试。
- NOT_RUN：文件符号链接用例；Linux/macOS 上的运行。
- OPEN / 阻塞：R4 独立复核（c08407d..HEAD）；vendor 范围决策；推送（需批准）。

## 7. R4 复核入口
- 范围：`git log c08407d..fix/skill-ins1-cli-v0.1.1`；`git diff c08407d fix/skill-ins1-cli-v0.1.1 -- skill/`。
- 命令：上表全部；再对旧版跑判别（`git show c08407d:skill/tools/install_skill.py > %TEMP%\old\install_skill_old.py`，设 VB_INSTALLER_UNDER_TEST，同理 VB_INIT_UNDER_TEST）。
- 夹具：test_install_skill.py 的伪源技能（SKILL.md + vendor 存根 verify_manifest.py）；test_vb_init_cli.py 把技能复制进临时项目 `.claude/skills/vibecoding`。
- 请尝试打破：链接在更深层/竞态替换；清单内含 `../` 或绝对路径；清单哈希被伪造为匹配；大小写不敏感文件名冲突；只读文件；--json 下的未预期异常；argparse `--help` 在 --json 下的行为；显式 `--standard` 为相对路径。

## 8. 下一步
1. 安排 R4 独立复核（不是开发者本人）。
2. Chris 决定 vendor 范围与是否推送两个分支。
3. 视需要在有权限的机器上补跑文件符号链接用例。

## 9. R5 轮（R4-N1/N2/N3 修复，开发者自测，非独立复核）
- 提交：a887cd9（安装器 N1+N3 + test_install_skill.py），9c91a9e（vb_init N2 + test_vb_init_cli.py），以及本文档提交。范围：`git log 5327eb9..fix/skill-ins1-cli-v0.1.1`。
- N1：plan_install 对每个文件检查所需父目录分量，`lexists 且非目录` → 冲突「所需目录位置被非目录占用」→ rc2，零写入（含 --force）。
- N3：guard 的 BoundaryError 不再降级为冲突，单独列出并 REFUSED rc1（与文档一致）；两个链接用例断言由 `!=0` 收紧为 `==1`。
- N2：`_compensate` 仅当当前内容 == 本进程写入值时才还原/删除，否则记 ResidualRisk；`_mkdirs` 把新建目录的 realpath 登记进 baseline，guard 对父路径校验 realpath 是否变化（识别指向项目内的 Junction 替换）；rollback 中越界/不可读/被他人改动的跳过项全部进残留，因此不会再输出「FAILED（已回滚」。不引入事务框架。
- 命令与退出码（Windows，Python 3.14.3）：
  | 命令 | 时点 | rc | 结果 |
  |---|---|---|---|
  | 全套 unittest discover | 改动前 5327eb9 | 0 | 78 OK（skip 1） |
  | verify_manifest（cwd=vendor） | 改动前 | 0 | PASS 33/0/0/0 |
  | 新/收紧用例 × 5327eb9（git show 到 %TEMP%\vbr5\old5327，VB_INSTALLER_UNDER_TEST / VB_INIT_UNDER_TEST） | 判别 | 1 | 8 运行：5 FAIL + 1 ERROR（V7：decoy/config.json 经 Junction 被删），1 skip（文件符号链接），1 PASS |
  | 同上 × 新版 | 判别 | 0 | 8 运行，0 FAIL，1 skip |
  | 全套 unittest discover | 改动后 | 0 | 83 OK（skip 1） |
  | verify_manifest | 改动后 | 0 | PASS 33/0/0/0 |
- R5 复核入口：重跑 R4 的 raw\atk_installer.py I1（文件占位 scripts）与 raw\atk_init.py V6/V7（mock `_replace`），对比 5327eb9 与 HEAD；尝试：更深层文件占位、补偿与回滚之间二次替换、文件符号链接（本机 NOT_RUN）、真实 TOCTOU 竞态（NOT_RUN）。
- 残留风险：TOCTOU 窗口仍在（检查—写入非原子）；N4..N10 仍 OPEN；文件符号链接、跨盘、Linux/macOS、user scope 仍 NOT_RUN。
