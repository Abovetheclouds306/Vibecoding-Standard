# 02 · 已有规则共存（AGENTS.md / CLAUDE.md / rules）

## 核心原则

**已有规则是用户的资产，不是本技能的输入。** 初始化只能"加一块"，不能"改一句"。任何需要改动既有表述的情况，都交回用户决定。

## 各平台入口与共存方式

| 入口文件 | 谁读 | 本技能的做法 |
| --- | --- | --- |
| `AGENTS.md` | Codex 原生；Cursor（作为规则来源之一）；多数 Agent 的通用约定 | 追加标记块；块外不动 |
| `CLAUDE.md` | Claude Code（Project instructions） | **从不编辑**，只给指令 |
| `.cursor/rules/*.mdc` | Cursor Rules（每次对话/匹配时注入） | 不编辑；提示用户 Rules 与 Skills 的分工 |
| `.cursor/skills/`、`.agents/skills/` | Cursor / Codex 的技能目录 | 安装技能时用（见 `06`） |
| `.github/copilot-instructions.md` | GitHub Copilot | 不编辑；如需覆盖，由用户决定 |

## `CLAUDE.md` 与 `AGENTS.md` 的关键冲突（易踩）

Claude Code 由「Project instructions」设置决定读取哪些文件，**默认仅当工作目录及其上方各层都没有 `CLAUDE.md` / `.claude/CLAUDE.md` / `CLAUDE.local.md` 时，才读取 `AGENTS.md`**。

后果：项目里一旦有 `CLAUDE.md`，注入到 `AGENTS.md` 的标记块**可能根本不会被 Claude Code 读到**。这不是本技能的 bug，是加载机制。

`vb_init.py` 检测到 `CLAUDE.md` 时输出以下两种解法之一（**由用户选择，脚本不代改**）：

1. 把 Project instructions 设置为同时读取两者（`claude-md-and-agents-md`）；
2. 在 `CLAUDE.md` **首行**加入 `@AGENTS.md` 显式导入。

验证方式：在 Claude Code 里用 `/context` 查看 Memory files 是否包含 `AGENTS.md`。

> 版本提示：官方最低版本与本机实测版本可能不同（本机自建网关环境实测 2.1.281 起才读 `AGENTS.md`）。属**环境观测值**，不要当通用边界。详见标准 `agents/Claude-Code.md` 的证据分级。

## 与 Rules 的分工（Cursor 视角）

| | Rules | Skills |
| --- | --- | --- |
| 用途 | 短约束（"新文件用 TypeScript"） | 多步骤流程（部署、审计、提交流程） |
| 长度 | 几行到几百行 | 可长，按需加载 |
| 生效 | 每次/匹配时进入上下文 | 按需调用（`/name`、`@name`）或自动匹配 |

因此：**别把本技能的流程塞进 Rules**。Rules 里最多放一句"本项目遵循 Vibecoding，见 `.vibecoding/`"，其余交给技能与脚本。

## 追加块长什么样

```markdown
<!-- vibecoding:begin v0.1.0 standard=1.2.7 -->
## 工程纪律（Vibecoding v1.2.7）

- 唯一规则真值源：规范正文，位置见 `.vibecoding/config.json` 的 `standard_vendor_path`；本文件只做入口。
- 该路径不可读＝技能已卸载或项目已移动：不得假装规范已加载，重装后重跑 `vb_init --apply` 重定位。
- 验证结论必须带命令与实际退出码；`0=PASS / 1=FAIL / 2=UNKNOWN`，`2` 不得当通过。
- 未运行的验证写 `NOT_RUN`，禁止写成 PASS。
- 会话中断前更新 `.vibecoding/HANDOFF.md`；新会话先读它。
- 更多：见技能 `references/03-task-flow.md`。
<!-- vibecoding:end -->
```

块内含版本号：标准或技能升级后，`vb_init.py` 会报告 `differs`，由用户确认后 `--update-block` 更新——**不会静默改**。

## 禁止事项

- 不把 `AGENTS.md` 改写成技能的镜像（会让用户失去自己的入口文件）。
- 不删除用户写的 `CLAUDE.md`、不覆盖 rules。
- 不在他人未提交改动上叠加自己的改动（先报告，再问）。
