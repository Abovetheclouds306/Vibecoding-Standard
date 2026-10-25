---
name: vibecoding
description: Apply the Vibecoding Standard v1.2.7 engineering discipline inside a software project. Use when starting or resuming development work in a repository, when a task needs verification evidence with exit codes, when initializing AGENTS.md or CLAUDE.md without overwriting existing rules, when handing off or recovering a session from repository evidence, or when the user mentions Vibecoding, 证据门禁, 会话交接, 最低工程动作集, or asks to follow the team engineering standard. Covers project identification, guarded init, task flow, evidence gates (0=PASS / 1=FAIL / 2=UNKNOWN, never report NOT_RUN as PASS) and handoff.
license: Proprietary. See vendor/vibecoding-standard/README.md for the standard's own terms.
compatibility: Requires git and Python 3.10+. Offline gates only; no network access required.
metadata:
  version: "0.1.0"
  standard_version: "1.2.7"
  standard_signoff_commit: "ce5b361cf13ae373094abe67eb9ce7a6e22ecb8f"
  standard_release_commit: "fd9750f3e6c4c2105cf253d5f7d6494f0f373fdf"
  standard_tag: "v1.2.7"
  standard_vendored_sha256: "0ce2a06cf506904cca4e0597240d43f5e869ee9845d7b508bc83a9fd2745dd38"
---

# Vibecoding Skill（v0.1.0 POC）

把 Vibecoding Standard v1.2.7 的工程纪律包装成可安装技能：**项目识别 → 受保护初始化 → 标准任务流程 → 证据与退出码门禁 → 交接与恢复**。

## 这个技能是什么，不是什么

- **是**：一个**流程编排层**。它判断当前处于哪个场景、该读哪份按需资料、该跑哪条确定性命令，并把结论落成可复核的证据文件。
- **不是**：不是母规范的第二副本。规则正文只有一份，位于 `vendor/vibecoding-standard/`，**与签收版本逐字节相同**（34 文件 blob 全等，可用其自带 `MANIFEST.sha256` 校验）。任何规则改动都必须回到标准仓库发版，本技能只整体替换 vendor 目录。
- **不是**：不是"装上就无人值守"。技能只能提高一致性，**不能保证**任何 Agent 一定激活它、一定遵循它；激活失败是已知风险，见 `references/06-platform-capabilities.md`。

## 铁律（任何场景都先满足）

1. **不覆盖既有规则**：`AGENTS.md` / `CLAUDE.md` / Cursor rules 等已有内容一律不改。初始化只允许写自己的标记块（`<!-- vibecoding:begin -->` … `<!-- vibecoding:end -->`），块外一个字节都不动。
2. **不假 PASS**：只有全部验证命令退出码为 `0` 才允许 `PASS`。未运行 → `NOT_RUN`（退出码 `2`），失败 → `FAIL`（`1`）。`2` 不得当通过，也不得当跳过。
3. **不碰他人改动**：不 `reset` / `checkout --` / `clean` / 强推；发现无关改动保留原样并报告。
4. **结论必须有证据**：口头结论不算交付；证据写进 `.vibecoding/evidence/<task>.md`，含命令、实际退出码、证据路径。
5. **交接写进仓库**：会话中断前更新 `.vibecoding/HANDOFF.md`；恢复时先读它，不靠记忆。

## 第一步：判断场景

| 观察到的情形 | 场景 | 先读 |
| --- | --- | --- |
| 项目里没有 `.vibecoding/`，也没有规范入口 | 首次接入 | `references/01-project-init.md` |
| 已有 `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/` | 共存接入（**只读判断**） | `references/02-existing-rules.md` |
| 已有 `.vibecoding/` 与 `HANDOFF.md` | 续接任务 | `references/05-handoff.md` |
| 正常开发任务（改代码 / 修 bug / 加测试） | 标准任务流程 | `references/03-task-flow.md` |
| 要交结论、要写验证记录 | 证据门禁 | `references/04-evidence-gate.md` |
| 需要知道某平台会不会自动激活 | 平台能力与限制 | `references/06-platform-capabilities.md` |

场景判断用只读命令完成，例如 `git rev-parse --show-toplevel`、`git status --porcelain`、`ls .vibecoding`。**判断阶段不写盘**。

## 三条确定性命令（唯一允许写盘的动作）

```bash
# 1) 受保护初始化：默认 dry-run，只在 --apply 时落盘；重复执行必须无变化
python <skill>/scripts/vb_init.py --project <项目> --apply

# 2) 门禁：跑验证命令 → 写证据 → 调标准自带 check_evidence.py → 汇总退出码
python <skill>/scripts/vb_gate.py --project <项目> --task <TASK-ID> --verify "<命令>"

# 3) 交接：写/读 HANDOFF.md，恢复时用它列出应复核的证据
python <skill>/scripts/vb_handoff.py --project <项目> --task <TASK-ID> --show
```

`<skill>` 是含本 `SKILL.md` 的目录（Claude Code 可用 `${CLAUDE_SKILL_DIR}`，实现无关写法见 `references/06`）。三条命令都是**幂等**的：重复执行不产生重复文件、不覆盖用户改动。

退出码语义统一：

| 码 | 含义 | 允许的说法 |
| --- | --- | --- |
| `0` | PASS，全部验证已运行且成功 | "已验证通过（附证据路径）" |
| `1` | FAIL，有确定失败 | "验证失败" + 失败项 |
| `2` | UNKNOWN，未运行 / 证据不足 / 需人工决定 | "未验证" —— **禁止**说成通过或跳过 |

## 按需加载（不要一次性全读）

| 文件 | 何时读 | 估算 |
| --- | --- | --- |
| `references/01-project-init.md` | 首次接入、要跑 `vb_init.py` 前 | 短 |
| `references/02-existing-rules.md` | 项目已有 AGENTS.md / CLAUDE.md / rules | 短 |
| `references/03-task-flow.md` | 执行任何开发任务 | 中 |
| `references/04-evidence-gate.md` | 写证据、判 PASS/FAIL、处理假 PASS | 中 |
| `references/05-handoff.md` | 交接、恢复、长任务跨会话 | 短 |
| `references/06-platform-capabilities.md` | 换平台、排查"技能没生效" | 中 |
| `vendor/vibecoding-standard/AI_PROJECT_STANDARD.md` | 需要**规则原文**时（唯一真值源，21 节） | 长，用 grep 定位 |

需要规则原文时的检索方式：

```bash
grep -n "第 8 节\|DoD\|证据" vendor/vibecoding-standard/AI_PROJECT_STANDARD.md | head -20
```

## 三层自动应用（本技能的定位）

1. **项目入口**（跨会话、跨 Agent 的最低纪律）＝ `.vibecoding/AGENTS.block.md` 注入到 `AGENTS.md` 的标记块。生效前提有两个：Agent 读 `AGENTS.md`，**且规范正文仍可被定位**——块里写明以 `.vibecoding/config.json` 的 `standard_vendor_path` 为准，并给出本次初始化解算出的实际路径。
   ⚠ **不能据此宣称"不安装技能也能使用完整规范"**：规范正文由**已安装技能的 vendor 副本**提供，项目内只有指针。技能被卸载或项目被移动后，这一层只能如实告知"规范位置未知"，此时必须重装技能并重跑 `vb_init --apply` 重定位。
2. **Agent Skill**（按任务自动激活的流程）＝ 本 `SKILL.md` ＋ `references/`。是否激活取决于宿主是否实现按 description 匹配，**不保证**。
3. **确定性工具**（不依赖模型判断）＝ `scripts/*.py`。这是唯一能真正阻止假 PASS 的一层；CI / pre-commit 里直接调 `vb_gate.py` 比指望模型自觉更可靠。

**禁止表述**：不得声称"安装本技能后即可无人值守持续运行"。真实限制见 `references/06-platform-capabilities.md` 的 NOT_RUN 清单。

## 改动边界

- 只写 `.vibecoding/` 与 `AGENTS.md` 的标记块；不写业务代码（业务改动由任务本身负责）。
- 不修改 `vendor/`（只读副本）；升级 = 整体替换并校验 `MANIFEST.sha256`。
- 不修改标准仓库、不推送、不触发 CI（除非用户当次明确授权）。
