# 01 · 项目识别与受保护初始化

## 目的

让一个新项目在**不动既有内容**的前提下获得跨会话的最低工程纪律，并把"这个项目遵循哪版标准"记录成可校验的事实。

## 识别（只读，先做）

```bash
git rev-parse --show-toplevel           # 是否在 Git 仓库内、真实根在哪
git status --porcelain                  # 是否脏（脏会影响能否安全写 tracked 文件）
ls -a | grep -E '^(AGENTS\.md|CLAUDE\.md|\.cursor|\.vibecoding)$'
```

判定顺序：

1. **不在 Git 仓库** → 可以初始化，但所有结论标注"无版本基线"，交接与证据里的 `Baseline` 写"无"。
2. **在 Git 仓库但 worktree 归属不明确** → 用 `git rev-parse --show-toplevel` 与 `git worktree list` 对齐路径，避免写错副本。
3. **已存在 `.vibecoding/`** → 不是首次接入，转 `05-handoff.md`，不要重复初始化。

## 执行初始化

```bash
python scripts/vb_init.py --project <项目>            # dry-run，只打印计划
python scripts/vb_init.py --project <项目> --apply    # 落盘
```

`vb_init.py` 会：

1. 定位标准正文（顺序：`--standard` 参数 → 本技能 `vendor/vibecoding-standard/` → 环境变量 `VB_STANDARD_HOME`）。
2. **校验标准副本**：调用标准自带的 `tools/verify_manifest.py`。不通过则拒绝初始化（退出码 `1`），不写入任何文件。
3. 生成 `.vibecoding/`：`config.json`、`AGENTS.block.md`、`evidence/_template.md`、`HANDOFF.md`（仅在不存在时创建）。
4. 处理 `AGENTS.md`：

| 现状 | 动作 | 状态 |
| --- | --- | --- |
| 不存在 | 创建，内容＝标记块 | `created` |
| 存在、无标记 | **追加**标记块（原有内容一字不改） | `appended` |
| 存在、有标记且内容相同 | 不动 | `unchanged`（幂等） |
| 存在、有标记但内容不同 | 不动，报差异 | `differs` → 退出码 `2`，需 `--update-block` 才改 |

5. **从不编辑 `CLAUDE.md`**。若存在，只输出共存指令（见 `02-existing-rules.md`），状态记 `manual_required`。

## 安全护栏

- 默认 **dry-run**；写盘必须显式 `--apply`。
- 目标文件中已有标记块且块外内容在两次运行之间变化 → 仍只动块内，块外保持原样。
- 工作区脏且要改 **tracked 文件**（如已提交的 `AGENTS.md`）→ 除非加 `--allow-dirty`，否则拒绝。
- 不删除任何文件；不生成时间戳命名的副本文件（避免"重复文件"）。
- 重复执行必须得到 `unchanged`。**若第二次执行出现 `appended` 或 `created`，视为缺陷**。

## 幂等性自检（交付前必做）

```bash
python scripts/vb_init.py --project <项目> --apply   # 第一次
git status --porcelain > /tmp/before.txt
python scripts/vb_init.py --project <项目> --apply   # 第二次
git status --porcelain > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt                   # 期望：无差异
```

期望输出：第二次全部 `unchanged`，`git status` 与第一次完全一致（不新增文件、不改内容）。

## 产物说明

| 路径 | 作用 | 是否可手改 |
| --- | --- | --- |
| `.vibecoding/config.json` | 记录标准版本、签收 commit、vendor 校验和、初始化时间 | 不建议（脚本比对用） |
| `.vibecoding/AGENTS.block.md` | 注入块的唯一来源，便于幂等比对 | 否（改注入块用 `--update-block`） |
| `.vibecoding/evidence/` | 任务证据，一任务一文件 | 是（由 `vb_gate.py` 生成，可人工补充） |
| `.vibecoding/HANDOFF.md` | 会话交接 | 是（`vb_handoff.py` 写，可人工补充） |
| `AGENTS.md` 标记块 | 跨会话最低纪律入口 | 块内由脚本维护，块外随便写 |
