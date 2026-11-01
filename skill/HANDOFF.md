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
  目标目录本身、其内任一分量、project scope 下项目根到目标之间任一分量是符号链接/Junction，或 realpath 越界 → rc1（不检查 user scope 的 ~ 及其上层、绝对或越出项目的 --path 的上层；见 §12）。写入/校验失败 → rc1 `FAILED`，只有成功才输出「安装完成」。
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
  | 全套 unittest discover | 改动前 5327eb9 | 0 | 78 OK，skipped=1（本 worktree 在 F: 盘实测 skipped=1，仅文件符号链接；跨盘用例在 F:↔%TEMP%(C:) 下实际运行。若仓库副本与 %TEMP% 同盘，跨盘用例也 skip → skipped=2，即 R5 的结果） |
  | verify_manifest（cwd=vendor） | 改动前 | 0 | PASS 33/0/0/0 |
  | 新/收紧用例 × 5327eb9（git show 到 %TEMP%\vbr5\old5327，VB_INSTALLER_UNDER_TEST / VB_INIT_UNDER_TEST） | 判别 | 1 | 8 运行：5 FAIL + 1 ERROR（V7：decoy/config.json 经 Junction 被删），1 skip（文件符号链接），1 PASS |
  | 同上 × 新版 | 判别 | 0 | 8 运行，0 FAIL，1 skip |
  | 全套 unittest discover | 改动后 | 0 | 83 OK，skipped=1（本 worktree 在 F: 盘实测 skipped=1，仅文件符号链接；跨盘用例在 F:↔%TEMP%(C:) 下实际运行。若仓库副本与 %TEMP% 同盘，跨盘用例也 skip → skipped=2，即 R5 的结果） |
  | verify_manifest | 改动后 | 0 | PASS 33/0/0/0 |
- R5 复核入口：重跑 R4 的 raw\atk_installer.py I1（文件占位 scripts）与 raw\atk_init.py V6/V7（mock `_replace`），对比 5327eb9 与 HEAD；尝试：更深层文件占位、补偿与回滚之间二次替换、文件符号链接（本机 NOT_RUN）、真实 TOCTOU 竞态（NOT_RUN）。
- 残留风险：TOCTOU 窗口仍在（检查—写入非原子）；N4..N10 仍 OPEN；文件符号链接、跨盘、Linux/macOS、user scope 仍 NOT_RUN。

## 10. R6 轮（R5-N2 测试补强 + R5-N5 计数更正，开发者自测，非独立复核）
- 提交：a1a32c8（skill/tests/test_vb_init_cli.py，新增 TestR5N2RealLocationAndRollbackResiduals 5 个用例），以及本文档提交。未改产品代码（新用例在 HEAD 上全部通过，未暴露新缺陷）。
- 用例：回滚前把目录换成指向项目内、内容逐字节相同副本的 Junction——E1 新建 .vibecoding、E2 预先存在的 .vibecoding、E3 新建的嵌套 .vibecoding/evidence、E7 同场景 --json（status=failed、rc=1）；断言副本不变、rc=1、有 ResidualRisk、无「FAILED（已回滚」。另有回滚前他进程改写 HANDOFF（保护 modified-by-others 残留）。
- 变异（%TEMP%\vbr6\mutate.py，替换串与 R5 raw\mutate_r5.py 相同，经 VB_INIT_UNDER_TEST 运行 test_vb_init_cli）：
  | 变异 | 结果 | 失败的新用例 |
  |---|---|---|
  | M4 去掉新建目录登记 baseline | KILLED | E1、E3、E7 |
  | M5 去掉父路径 realpath 比对 | KILLED | E1、E2、E3、E7 |
  | M6 去掉回滚越界残留 | KILLED | E1、E2、E3、E7 |
  | M7 去掉回滚被他人改动残留 | KILLED | modified_by_others_at_rollback |
  HEAD：18/18 OK；5327eb9：新 5 例全部 FAIL。
- 全套 unittest discover：rc=0，88 OK，skipped=1（本 worktree，原因见 §9 注）。verify_manifest（cwd=vendor）：rc=0，PASS 33/0/0/0。
- R6 复核入口：范围 `git log c1ae6e3..fix/skill-ins1-cli-v0.1.1`；在独立副本上用 R5 raw\mutate_r5.py 的 M4–M7 重跑全套与 test_vb_init_cli，确认四个变异均 KILLED、HEAD 全绿；R5-N1/N3/N4 仍 OPEN 未修。
- NOT_RUN：文件符号链接、真实 TOCTOU 竞态、跨盘（在同盘副本中）、Linux/macOS（Junction 用例在非 Windows 下 skip）、user scope。

## 11. R7 轮（R4-N4..N10、R5-N1/N3/N4、R6-N2，开发者自测，非独立复核）
- 范围：`git log 6250adb..fix/skill-ins1-cli-v0.1.1`。开发临时目录：%TEMP%\vbdev_r7（旧版副本 old6250\，变异 mut\ 与 mutate_r7.py）。
- 提交：6a0d17a R4-N4；56c60fe R4-N5；1900fd9 R5-N1；ace30ec R4-N10（均为 tools/install_skill.py + tests/test_install_skill.py）；608118c R4-N9；d2a83c3 R4-N6；691f4dc R4-N8/R5-N3（均为 vibecoding/scripts/vb_init.py + tests/test_vb_init_cli.py）；337aef1 R6-N2（仅 tests/test_vb_init_cli.py）；以及本文档提交。
- 行为变化：dest 被文件占据由 REFUSED rc1 改为冲突 rc2（R5-N1）；--json 下前缀缩写不再被接受。
- 判别：新增 17 例 × 6250adb → 14 FAIL、3 PASS（R4-N10 内层 Junction 与 R6-N2 两例为变异保护用例，旧版本来就正确）；× HEAD 全部 PASS。
- 变异（python %TEMP%\vbdev_r7\mutate_r7.py，经 VB_INSTALLER_UNDER_TEST / VB_INIT_UNDER_TEST）：A 去掉链路分量链接检查、B overlap=False、C 去掉非目录占用检查、D 清单键不过滤、E `_inside` 恢复旧拼接、F allow_abbrev=True、G 补偿 guard 失败仍 _describe、H 不撤销已收敛残留、M2（R5）边界降级为冲突、M7（R5）去掉被他人改动残留——全部 KILLED。
- 全套 unittest discover（cwd=skill\tests）：rc=0，105 OK，skipped=1；verify_manifest（cwd=vendor）：rc=0，PASS 33/0/0/0。
- 待 Owner 决定：R4-N7（固定标准哈希）、R4-N6 余项（--json --help 的 status、KeyboardInterrupt）。
- R7 复核建议：用独立副本重跑上述变异；尝试 --project 为相对路径/含 `..` 时的分量检查、--path 为绝对路径（跳过链路检查，仅 dest 自身与 guard）、user scope、盘符根实写（本轮仅函数级）。
- NOT_RUN：文件符号链接（WinError 1314）、真实 TOCTOU 竞态、user scope、Linux/macOS、盘符根实际写入。
