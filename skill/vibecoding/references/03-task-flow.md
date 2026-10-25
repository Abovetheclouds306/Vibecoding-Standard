# 03 · 标准开发任务流程

## 最低工程动作集（不需要判断力，每次必做）

**开工前**

1. 读项目入口：`AGENTS.md`（或 `CLAUDE.md`）、`.vibecoding/config.json`、`.vibecoding/HANDOFF.md`。
2. 确认基线：`git rev-parse --abbrev-ref HEAD`、`git rev-parse HEAD`、`git status --porcelain`。
3. 确认边界：允许改哪些路径、验证命令是什么、谁验收。**没写清就先问。**

**交付前**

4. 跑验证命令，记**实际退出码**（不是"应该通过"）。
5. 写证据到 `.vibecoding/evidence/<TASK>.md`（用 `vb_gate.py` 生成）。
6. 更新 `.vibecoding/HANDOFF.md`（用 `vb_handoff.py`）。
7. 报告里给：改了什么文件、验证结果、证据路径、未完成项。

## 标准流程（六步）

```
识别场景 → 读入口 → 小步改 → 跑验证 → 落证据 → 写交接
```

### 1. 识别场景
见 `SKILL.md` 的场景表。首次接入先跑 `vb_init.py`；已有 `.vibecoding/` 直接续接。

### 2. 读入口（而不是读全部规范）
只读三样：项目入口文件、`config.json`、`HANDOFF.md`。规则原文按需 grep：

```bash
grep -n "第 8 节" .vibecoding/vendor/vibecoding-standard/AI_PROJECT_STANDARD.md 2>/dev/null \
  || grep -n "第 8 节" <skill>/vendor/vibecoding-standard/AI_PROJECT_STANDARD.md
```

### 3. 小步改
- 一次只做一类改动；改动前先用 `git status` 确认没有夹带他人改动。
- 新增文件优先，改既有文件要有明确理由。
- 临时脚本放项目内隔离目录（如 `.vibecoding/tmp/<TASK>/`），交付前清理或正式化。

### 4. 跑验证
- 用项目**自己声明的**命令（README / AGENTS.md / 测试文件），不要自创一套。
- 记录：命令原文、实际退出码、输出摘要、耗时。
- 失败不要立刻"调整预期"——先判断是代码错还是断言错。**为了让门禁变绿而放宽断言，属禁止行为。**

### 5. 落证据
一个任务一份：`.vibecoding/evidence/<TASK>.md`。字段集由标准的 `check_evidence.py` 强制校验，见 `04-evidence-gate.md`。

### 6. 写交接
不是可选动作。写成"下一个 Agent 只看仓库就能继续"的程度：基线、已改文件、验证结果、阻塞与解除条件、恢复步骤。

## 复杂度分级（决定要不要加反向审查）

| 任务特征 | 建议动作 |
| --- | --- |
| 单文件、单点、可一眼看完 | 自查即可，证据一行结论 |
| 多验收条件 / 多分支 / 跨模块 | 交付前做**反向遗漏审查**：从原始需求与风险反推"我漏了什么"，写进证据 |
| 有外部副作用（写库、发消息、部署） | 必须列副作用清单 + 回滚方式 |

## 常见反模式

| 反模式 | 为什么坏 | 正确做法 |
| --- | --- | --- |
| "测试应该能过"就写 PASS | 假 PASS，事后无法追责 | 记录实际退出码 |
| 只跑了一个测试就宣称全绿 | 覆盖面谎报 | 跑全量或明示"仅跑了 X" |
| 未运行项写"跳过" | `2` 被当成通过 | 写 `NOT_RUN` + 原因 |
| 交接写"见聊天记录" | 新会话没有聊天记录 | 写进 `HANDOFF.md` |
| 为了变绿放宽断言 | 掩盖缺陷 | 保留断言，判 FAIL 并说明 |
