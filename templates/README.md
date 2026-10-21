# 模板选用指引（Vibecoding v1.2.5）

模板是**可复制的工程文件骨架**，不是说明书集合。只复制你需要的；复制后**删掉不适用的小节、填实所有占位符**（把 `<……>` 换成真实值，未知值显式标"待确认"，不要留着占位符）。

用哪些模板由母规范的「文档职责」（第 4 节）与「按规模采用」（第 5 节）决定。

## 一、基础 —— 新项目最小可用

对应第 5 节「小项目」，四项即可启动：

| 模板 | 对应母规范 | 作用 |
| --- | --- | --- |
| `AGENTS.md.template` | §3 / §4 | 跨 Agent 规则入口：真值源映射、修改边界、命令入口、交接规则 |
| `README.md.template` | §4 | 项目入口与快速启动 |
| `TODO.md.template` | §7 | **唯一**任务表（已有 Task Board 时改为索引） |
| `development.md.template` | §4 | 实际环境、启动、测试、构建命令 |

## 二、按需 —— 中大型项目 / 特定用途

对应第 5 节「中型项目」与「长期或多人项目」：

| 模板 | 何时用 |
| --- | --- |
| `project-overview.md.template` | 需要交代目标、范围、术语、约束 |
| `architecture.md.template` | 有模块划分或数据流需要固定 |
| `SPEC-template.md.template` | 需求复杂、验收需要独立条目（§10） |
| `STATUS.md.template` | 需要能力与验证快照（§3；**不得**变成第二份任务表） |
| `PROGRESS.md.template` | 需要跨会话的执行历史（§3，只追加事实） |
| `ROADMAP.md.template` | 存在跨阶段目标 |
| `DESIGN.md.template` | UI / 游戏类项目 |
| `component-api.md.template` | 有稳定对外接口 |
| `user-guide.md.template` | 有终端使用者 |

## 三、专项 —— 特定机制或审计要求

| 模板 | 何时用 |
| --- | --- |
| `ADR-template.md.template` | 重要架构或兼容性决定（§10） |
| `EVIDENCE-template.md.template` | 需要独立、可定位的验证证据记录（§9） |
| `HANDOFF.md.template` | 复杂任务的独立交接记录（§17）；简单任务写在任务记录或 PROGRESS 即可 |
| `TRACEABILITY.md.template` | 跨模块或审计要求下的追踪索引（§18） |
| `CLAUDE.md.template` | 使用 Claude Code 且确需 `CLAUDE.md` 入口时（见 `agents/Claude-Code.md`） |

## 四、不要做的事

- 不批量把所有模板复制到每个项目。
- 不为格式整齐强行迁移旧代码与文档。
- 不堆空模板（母规范第 14 节「避免的模式」）。
- 同一类信息只保留一个权威来源，不新开第二份任务表。
