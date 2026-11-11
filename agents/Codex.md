# Codex 接入 — Vibecoding v1.2.8

适用：Codex。Claude Code 见 [`Claude-Code.md`](Claude-Code.md)。

本文件**只描述 Codex 特有的操作差异**。跨 Agent 的业务规则、任务、验收与证据一律以项目 `AGENTS.md` 指向的权威文档为准 —— 本文件不构成第二份真值源。

---

## 1. 接入方式

Codex 原生读取项目根目录的 `AGENTS.md`，**无需额外入口文件**，也不要在项目根额外创建 `CLAUDE.md` 之类的适配层。

在项目 `AGENTS.md` 的「真值源映射」中登记本规范的路径（`Vibecoding规范/AI_PROJECT_STANDARD.md`）与项目的 Spec / 架构 / 任务板 / 验证命令入口，即可让 Codex 与本规范对齐。

## 2. 首次接入提示词（可直接复制）

```text
阅读当前仓库的 AGENTS.md，按其中的真值源映射找到任务、规格与开发命令。检查当前代码与文档是否一致，补齐本次任务需要的缺口，保留已有结构。

然后完成指定任务，执行必要验证，记录证据并同步任务状态。未执行的验证标记 NOT_RUN。

交付前按母规范 §8.1 从原始需求和风险反向检查遗漏；记录范围、限制和处置结果，不把自查或字段齐全当作独立 Review。
```

在其后补充 `本次指定任务：TASK-xxx`，或直接写清目标与验收标准。实施时同时遵守 `AGENTS.md` 指向的母规范。

## 3. 日常执行（可直接复制）

```text
按 AGENTS.md 执行 TASK-xxx，完成验证并交接。
```

`TASK-xxx` 替换为唯一任务来源中的 ID。已有 Task Board 时继续引用它，不额外建立第二份 TODO。

## 4. 执行边界

没有指定任务时先澄清范围或报告待办，不自行对所有项目执行迁移。真实写入、删除、部署、外部服务调用应遵守项目授权与清理规则。验证结果区分 `PASS / FAIL / BLOCKED / NOT_RUN`，未执行不得写 `PASS`。

## 5. 与 Claude Code 的协作

两者共用同一个任务板、Spec 与证据路径，任务 ID 相同。交接要求见母规范 §17 与 [`Claude-Code.md`](Claude-Code.md) 第 6 节。
