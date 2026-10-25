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

1. 定位标准正文（顺序：`--standard` 参数 → 环境变量 `VB_STANDARD_HOME` → 技能内置 `vendor/vibecoding-standard/` → 项目内 `.vibecoding/vendor/vibecoding-standard/`）。
2. **校验规范接入**（见下节）：vendor 必须实际存在、正文可读、`MANIFEST.sha256` 与 `tools/verify_manifest.py` 齐备。任一缺失即报**接入缺失**并拒绝初始化，**不写指向空路径的注入块**。
3. **校验标准副本**：调用标准自带的 `tools/verify_manifest.py`。不通过则拒绝初始化（退出码 `1`），不写入任何文件。
4. 生成 `.vibecoding/`：`config.json`、`AGENTS.block.md`、`evidence/_template.md`、`HANDOFF.md`（仅在不存在时创建）。
5. 处理 `AGENTS.md`：

| 现状 | 动作 | 状态 | 退出码 |
| --- | --- | --- | --- |
| 不存在 | 创建，内容＝标记块 | `created` | `0` |
| 存在、无标记 | **追加**标记块（原有内容一字不改） | `appended` | `0` |
| 存在、有标记且内容相同 | 不动 | `unchanged`（幂等） | `0` |
| 存在、有标记但内容不同 | 不动，报差异 | `differs` + `skipped(需 --update-block)` | **`2`** |
| 同上 + `--update-block` | **更新块内内容**，块外一字不动 | `differs` + `block_updated` | **`0`** |

> **退出码以操作完成后的真实状态为准**：`--update-block` 成功即表示"待你决定的事项已经决定并执行"，因此返回 `0`，横幅同步显示 `OK（标记块已更新）`。只有当差异**尚未**被授权处理时才返回 `2`。写入失败则返回非零，绝不冒充成功。

6. **从不编辑 `CLAUDE.md`**。若存在，只输出共存指令（见 `02-existing-rules.md`），状态记 `manual_required`（属提示，不改变退出码）。

## 规范定位与"接入缺失"（重要）

本技能**不复制整份规范到项目里**（否则会出现第二套规则副本）。规范正文始终来自**已安装技能的 vendor 副本**，项目里只记录"它在哪里"。

- 注入块里写明两件事：**以 `.vibecoding/config.json` 的 `standard_vendor_path` 字段为准**，以及**本次初始化时解算出的实际路径**。
- `standard_vendor_path` 的形态：
  - 技能装在项目内（如 `<项目>/.claude/skills/vibecoding/`）→ 记**项目相对路径**，随项目整体移动仍有效。
  - 技能装在项目外 → 记**绝对路径**，并标注"与本机安装位置绑定，换机器/移动技能后失效，需重新 `--apply` 重定位"。
- **不得宣称"不安装技能也能使用完整规范"**：技能被卸载或项目被移动后，该项目入口只能告诉你"规范位置未知"。此时正确动作是重装技能并重跑 `--apply`，**而不是**假装规范已加载、引用没读到的条款。

自检（不调用技能、只读项目文件即可完成）：

```bash
python -c "import json;print(json.load(open('.vibecoding/config.json'))['standard_vendor_path'])"
```


## 安全护栏

- 默认 **dry-run**；写盘必须显式 `--apply`。
- **写盘前预检**（任一不过即拒绝，且此时**尚未写任何文件**）：项目目录存在且是目录、所有目标路径都在项目目录内、`.vibecoding` 与 `.vibecoding/evidence` 若已存在必须是目录、`AGENTS.md` 若已存在必须是文件（不是目录）、项目目录可写。
- **写入前实时边界复核**：每次实际写入/删除/回滚前，重新核对目标**真实位置**必须在项目内；若预检后该路径被替换为符号链接 / Junction / 其他重解析点（或真实位置发生变化），**立即拒绝继续初始化并非零退出**，不跟随被替换的路径去动项目外数据。回滚、以及单条写入失败后的**就地补偿还原**同样受此约束：复核不过就停手并登记 `ResidualRisk`，不因"要还原"而放行。
- 目标文件中已有标记块且块外内容在两次运行之间变化 → 仍只动块内，块外保持原样。
- 工作区脏且要改 **tracked 文件**（如已提交的 `AGENTS.md`）→ 除非加 `--allow-dirty`，否则拒绝。
- 不删除任何文件；不生成时间戳命名的副本文件（避免"重复文件"）。
- 重复执行必须得到 `unchanged`。**若第二次执行出现 `appended` 或 `created`，视为缺陷**。
- 写盘顺序：先建 `.vibecoding/` 目录 → `config.json` → `AGENTS.block.md` → `evidence/_template.md` → `HANDOFF.md` → **最后**才动用户 `AGENTS.md`（缩短"用户文件已被改"的时间窗）。

## 失败与回滚

写盘统一记入内部日志（`WriteJournal`），并遵守四条硬约定：

1. **先登记后写**：条目（含原始字节）在写入动作之前就已落账，所以"写了一半"的文件也在回滚范围内，不会被漏掉。
2. **单条写入原子**：内容先写同目录临时文件，再 `os.replace` 原子替换。因此单条写入失败**不会留下半截目标文件**——目标要么是旧内容，要么是新内容。
3. **回滚如实报告**：无法还原时输出 `ResidualRisk <路径>`、失败原因与**实际残留状态**（字节数与哈希），且此时横幅显示 `回滚不完整，存在残留`，**不会**打印"已全部回滚"。
4. **补偿也走边界复核**：单条写入失败后先就地补偿（有原内容则写回、本次新建则撤销）。补偿同样是一次"改动目标"，写回/删除前必须重新核对真实位置；被替换成指向项目外的重解析点就**停手并记 `ResidualRisk`**，不做"跟随过去还原"。

**可控异常**（权限不足、磁盘错误、目标被占用等）发生时：

1. 按**逆序**回滚本次写入：本进程**新建**的文件删除、本进程**修改**的文件还原为原字节、本进程新建且已空的目录清理；
2. 若某文件在回滚前**已被其他进程改动**，则**跳过并报告** `Skipped(modified-by-others)`，绝不覆盖他人改动；
3. 打印可定位诊断（失败步骤、异常类型、异常信息、逐条回滚动作）并返回**退出码 1**；
4. 不会出现"部分失败却报 OK"的情况——只要回滚路径被触发，结论一定不是 PASS。

**边界（如实声明）**：进程被强杀（SIGKILL）、断电、文件系统自身非原子行为等**无法捕获/无法保证**的情形**不在**回滚承诺范围内；本脚本不做跨文件原子提交，也**不宣称"任何异常都零残留"**。这类场景的正确恢复方式是重新执行一次 `--apply`（幂等），必要时用 `git status` 核对残留。

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
| `.vibecoding/config.json` | 记录标准版本、签收 commit、vendor 校验和、**`standard_vendor_path`（规范正文的实际位置，项目内记相对路径 / 项目外记绝对路径）**、初始化时间 | 不建议（脚本比对用） |
| `.vibecoding/AGENTS.block.md` | 注入块的唯一来源，便于幂等比对 | 否（改注入块用 `--update-block`） |
| `.vibecoding/evidence/` | 任务证据，一任务一文件 | 是（由 `vb_gate.py` 生成，可人工补充） |
| `.vibecoding/HANDOFF.md` | 会话交接 | 是（`vb_handoff.py` 写，可人工补充） |
| `AGENTS.md` 标记块 | 跨会话最低纪律入口 | 块内由脚本维护，块外随便写 |

> 注意：`.vibecoding/vendor/` **不会**被创建。规范正文不在项目里，位置见 `config.json.standard_vendor_path`。
