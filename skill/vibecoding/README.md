# vibecoding（v0.1.0 POC）— 安装与使用

把 Vibecoding Standard v1.2.7 的工程纪律包装成可安装 Agent Skill。**规则只有一份**（`vendor/vibecoding-standard/`，与签收版本逐字节相同），本技能只负责流程编排与确定性门禁。

## 一、安装（按平台选路径）

把整个 `vibecoding/` 目录（含 `SKILL.md`）复制到目标位置。

| 平台 | 项目级 | 用户级 |
| --- | --- | --- |
| Claude Code | `<repo>/.claude/skills/vibecoding/` | `~/.claude/skills/vibecoding/` |
| Codex | `<repo>/.agents/skills/vibecoding/` | `~/.agents/skills/vibecoding/` |
| Cursor | `<repo>/.cursor/skills/vibecoding/` 或 `.agents/skills/vibecoding/` | `~/.cursor/skills/vibecoding/` |
| WorkBuddy | `<repo>/.codebuddy/skills/vibecoding/`（文档口径）或 `.workbuddy/skills/`（内置指引口径） | `~/.codebuddy/skills/` 或 `~/.workbuddy/skills/` |

> WorkBuddy 用户级路径存在两套文档口径，本机两个目录都存在。安装脚本用 `--target` 显式指定，避免靠猜。

一键安装（本仓库附带脚本，只做复制 + 校验，不改系统配置）：

```bash
python skill/tools/install_skill.py --target claude-code --scope project --project <项目>
python skill/tools/install_skill.py --target codex       --scope user
python skill/tools/install_skill.py --target workbuddy   --scope project --project <项目> --path .codebuddy/skills
python skill/tools/install_skill.py --target cursor      --scope project --project <项目> --dry-run
```

## 二、首次使用（三步）

```bash
# 1) 初始化（默认 dry-run，先看计划）
python <skill>/scripts/vb_init.py --project <项目>
python <skill>/scripts/vb_init.py --project <项目> --apply

# 2) 干活，然后过门禁（跑真实验证并写证据）
python <skill>/scripts/vb_gate.py --project <项目> --task T-001 \
  --verify "python -m unittest discover -s tests -v" \
  --verify "python -m compileall -q src"

# 3) 交接（中断前写，恢复时读）
python <skill>/scripts/vb_handoff.py --project <项目> --task T-001 \
  --done "..." --verify "..." --blocked "..." --next "..."
python <skill>/scripts/vb_handoff.py --project <项目> --show
```

## 三、Agent 用法（两种）

**自动**：不点名，直接派任务。宿主若按 description 匹配到本技能，会读 `SKILL.md` 并按其流程执行。**不保证**一定激活。

**显式**：

| 平台 | 写法 |
| --- | --- |
| Claude Code | 消息开头 `/vibecoding 初始化这个项目` |
| Codex | `/skills` 选择，或 `$vibecoding` |
| Cursor | `/vibecoding` 或 `@vibecoding` |
| WorkBuddy | `/vibecoding` 或从技能面板添加 |

## 四、验证技能自身

```bash
python scripts/vb_init.py --project <空目录> --skip-standard-check   # 冒烟
python vendor/vibecoding-standard/tools/verify_manifest.py           # 标准副本完整性
```

## 五、退出码

| 码 | 含义 |
| --- | --- |
| 0 | PASS：全部验证已运行且成功 |
| 1 | FAIL：有确定失败，或工具拒绝执行（如标准副本校验不过） |
| 2 | UNKNOWN：未运行 / 证据不足 / 需人工决定（**不得当通过**） |

## 六、已知限制

- 装上**不等于**一定激活、也不等于模型一定遵循；唯一强保障是 `vb_gate.py` 进 CI / pre-commit。
- 不支持无人值守持续运行（无守护进程、不轮询、不自动提交）。
- `vb_gate.py` 的 `--verify` 命令按宿主 shell 语义执行，跨平台写法请自行保证。
- Cursor 与 WorkBuddy 的真实自动激活在本 POC 中未实测（见 `references/06-platform-capabilities.md`）。
