# Claude Code 接入 — Vibecoding v1.2.8 候选

适用：Claude Code。Codex 见 [`Codex.md`](Codex.md)。

本文件**只描述 Claude Code 特有的加载与操作差异**。跨 Agent 的业务规则、任务、验收与证据一律以项目 `AGENTS.md` 指向的权威文档为准 —— 本文件不构成第二份真值源，也不建立平行任务系统。

---

## 1. 指令文件如何加载（最要紧的一节）

Claude Code 通过「**Project instructions**」设置决定读取哪些指令文件。默认值 `claude-md-or-agents-md` 的语义是：

> 读取 `CLAUDE.md`；**只有当工作目录及其上级目录中都不存在 `CLAUDE.md` 时**，才读取 `AGENTS.md`。

**判定范围（这是最容易踩错的地方）**：

| 会使 `AGENTS.md` 不被读取 | 不影响 `AGENTS.md` 读取 |
| --- | --- |
| 工作目录**或其上方任意一层**的 `CLAUDE.md` | 用户级 `~/.claude/CLAUDE.md` |
| 同目录或上方的 `.claude/CLAUDE.md` | 组织托管的 `CLAUDE.md` |
| 同目录或上方的 `CLAUDE.local.md` | `.claude/rules/*.md` |

⇒ **要保证 `AGENTS.md` 生效，必须确认工作目录及其上方的每一层都没有 `CLAUDE.md` 类文件。只检查当前项目目录是不够的。**

**四种取值**：

| `Project instructions` | Claude 读取 |
| --- | --- |
| `claude-md-or-agents-md`（默认） | `CLAUDE.md`；仅当工作目录及其上方均无 `CLAUDE.md` 时读 `AGENTS.md` |
| `claude-md-and-agents-md` | 两者都读（同目录先 `CLAUDE.md` 后 `AGENTS.md`；已加载过的 `AGENTS.md` 不重复读） |
| `claude-md` | 只读 `CLAUDE.md` |
| `managed-only` | 只读组织托管配置与自动记忆 |

**设置方式**：会话内 `/config`；或写进 `~/.claude/settings.json`（该条目**只从用户级、`--settings` 文件或托管配置读取，项目级与本地 settings 中的同名条目会被忽略**）：

```json
{
  "pluginConfigs": {
    "cc-plugin-agents-md@builtin": {
      "options": { "instructionFiles": "claude-md-and-agents-md" }
    }
  }
}
```

> v2.1.285 之前插件 ID 为 `agents-md@builtin`；v2.1.285 及以后两个 ID 都识别。

**两者共存的两种做法**（任选其一）：

1. 把 `Project instructions` 设为 `claude-md-and-agents-md`；
2. 让 `CLAUDE.md` 首行 `@AGENTS.md` 显式导入（导入**不会**导致重复读取）。Windows 上优先用 `@AGENTS.md` 导入而非符号链接 —— 建软链需要管理员权限或开发者模式。

**其他差异（与 `CLAUDE.md` 相比）**：

| 项 | `CLAUDE.md` | 经设置读取的 `AGENTS.md` |
| --- | --- | --- |
| `InstructionsLoaded` hook | 触发 | **不触发**（若由 `CLAUDE.md` 导入或软链，则照常触发） |
| `--add-dir` 目录（设 `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` 时） | 其 `CLAUDE.md` 加载 | 其 `AGENTS.md` **不加载** |
| 工作目录之外的 `@path` 导入 | 提示批准 | 仅在此前已批准时加载，不提示 |

另：`AGENTS.local.md`、`AGENTS.override.md`、`.agents/` 目录下的文件一律不会被读取。

## 2. 证据分级（请按级引用，不要把本地观测当通用规则）

| 断言 | 级别 |
| --- | --- |
| §1 全部加载语义、四种取值、`--add-dir` / hook / `@path` 差异、"或上方任意一层" | **OFFICIAL_DOCUMENTED** |
| 直接读取 `AGENTS.md` 的最低版本为 **v2.1.277** | **OFFICIAL_DOCUMENTED** |
| v2.1.280 之前 `/memory` 与 `/context` 不列出直接读取的 `AGENTS.md` | **OFFICIAL_DOCUMENTED** |
| 非标准会话（官方举例：Amazon Bedrock、禁用遥测）在 v2.1.281 之前只读 `CLAUDE.md` | **OFFICIAL_DOCUMENTED** |
| 本机实测：2.1.100 / 2.1.276 / 2.1.277 / 2.1.280 不读取，2.1.281 起读取 | **LOCALLY_VERIFIED**（仅 Windows + 本机自建网关 + 默认配置，各端复验 2 次） |
| 其他平台、其他 `Project instructions` 取值下的具体行为 | **UNVERIFIED** |

> 依据来源：Anthropic 官方文档 *How Claude remembers your project*（`docs.anthropic.com/en/docs/claude-code/memory`），2026-10-16 查阅。
>
> ⚠ **不要把本机实测的 2.1.281 当作通用版本边界**。官方口径是 **v2.1.277**；本机差异最可能来自"非标准会话"这一类（本机通过自建网关访问）。**VERSION_DEPENDENT 的内容请以官方文档为准，并用 §3 的方法在本机现测。**

## 3. 如何验证真的加载了

1. 运行 `/context`，查看 **Memory files** 列表 —— 列出的才是真正进入上下文的。
   - v2.1.280 之前该列表不显示直接读取的 `AGENTS.md` ⇒ 改为直接询问 Claude 其 project instructions 内容。
2. 需要可复现的独立证据时，用**内容敏感探针**：在项目里放一个不可猜的口令，问 Agent 该口令是什么（未命中要求回答"未知"）。禁用工具可排除"Agent 自己翻文件"造成的假阳性。方法见母规范 §9「验证证据」与项目自身的验证约定。

## 4. 首次接入提示词（可直接复制）

```text
先读取项目根目录的 AGENTS.md（包括将修改目录的局部规则），以及其中指向的 Vibecoding 规范、README、Spec、ADR、任务板与开发命令。

确认本次唯一任务 ID、当前代码与工作区状态、允许修改路径、验收标准，以及需要实际执行的验证。复用已有任务系统，禁止另建平行 TODO 或 Task Board。

在最小必要范围内实现目标；不顺带重构邻近代码，不无依据添加抽象，不假设结果。

运行适用验证，记录命令、版本、证据与 PASS / FAIL / BLOCKED / NOT_RUN。交付前按母规范 §8.1 从原始需求和风险反向检查遗漏；未执行的验证不得写 PASS，必要验收未通过不得标 DONE。

最后同步受影响的权威文档、任务状态与交接记录，明确剩余风险与尚未执行的检查。
```

## 5. 日常执行（可直接复制）

```text
按项目 AGENTS.md 执行 TASK-xxx，遵循同一任务板与母规范，在允许路径内最小改动，执行必要验证并交接；未运行标 NOT_RUN，未满足验收不得 DONE。
```

## 6. 交接

Codex 与 Claude Code 使用**相同的任务 ID 与证据路径**。交接时说明分支 / worktree、改动文件、已通过与未执行的验证、阻塞与剩余风险。真实写入、数据删除与外部系统操作需项目授权。
