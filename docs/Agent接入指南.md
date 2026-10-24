# 将 Vibecoding 规范接入自己的 AI Agent

> 适用版本：**Vibecoding Standard v1.2.7 候选**（本指南随同规范版本更新）。本文是**接入操作指南**，不是新的母规范。治理要求以 [`../AI_PROJECT_STANDARD.md`](../AI_PROJECT_STANDARD.md) 为准；Codex / Claude Code 特殊机制分别以 [`../agents/Codex.md`](../agents/Codex.md)、[`../agents/Claude-Code.md`](../agents/Claude-Code.md) 为准。

## 一、最推荐：直接把规范交给 Agent，让它帮你接入

**这就是最省事的方式。** 不必自己先研究 Skill、MCP 或逐项配置，也**不需要每次派任务都让 Agent 再去 GitHub 看规范**。只需在**每个业务项目首次接入时**，把规范仓库地址（或本地完整规范包）与下面的指令交给当前项目的 Codex、Claude Code 等编程 Agent，由它完成接入与自测。

**操作步骤：**

1. 在**需要接入的业务项目目录**启动 Agent，而不是在规范仓库里启动；确认它当前使用的是正确的项目和工作区。
2. 向 Agent 发送下面这段可直接复制的提示词。Agent 能访问私有 GitHub 时提供仓库地址；没有权限时给它本地解压后的规范路径或完整 ZIP，**不要粘贴个人 Token 到聊天、提示词或代码中**。
3. 接入完成后查看它的修改清单和验证证据；首次选一个离线、只读或低风险的任务试运行。通过后日常直接派任务即可。

### 直接发给 Agent 的接入提示词

```text
请在当前业务项目中接入我的统一工程规范 Vibecoding Standard v1.2.7 候选。

规范私有仓库：https://github.com/Abovetheclouds306/Vibecoding-Standard
如果你无法访问私有仓库，请先检查我提供的本地规范目录或正式 ZIP；仍不可访问时如实报告 BLOCKED，不得猜测或伪称已读取。

请自主推进到完成或明确阻塞：
1. 阅读规范 README.md、docs/Agent接入指南.md、AI_PROJECT_STANDARD.md，以及对应的 agents/ 说明。
2. 检查当前项目已有的 AGENTS.md、CLAUDE.md、局部规则、任务板、Spec、测试命令、分支/worktree 和未提交修改；先确认归属与冲突。
3. 按指南选择适合当前环境的最简单方式，把固定版本的规范接到当前项目的实际 Agent 入口；记录来源、规范版本及完整 Git commit SHA。保留原有业务约束，不创建平行规则或任务系统，不覆盖他人文件。
4. 核验规范文件可读取、入口实际生效、任务真值源和授权范围明确；在可行条件下用一项离线/只读/低风险任务验证执行、证据、交接和临时文件治理。区分“文件存在”“实际加载”“行为遵守”，未运行的检查记 NOT_RUN。
5. 交付：修改文件清单、规范版本/commit、接入方式、验证命令与结果、剩余限制，以及我今后最简短的日常使用指令。

仅授权当前项目内必要的接入文件修改与离线验证；未经单独授权，不做真实业务写入、不删未知归属文件、不推送远程、不合并或部署。不为了接入而重构业务框架。无需每个小步骤询问，遇到权限或安全边界再报告。

目标：一次接入、后续直接派任务；不要求我每次手动重复阅读规范的提示词。
```

**成功标志**：Agent 能说明本项目采用的规范版本与**实际可读取路径**、唯一任务来源、允许修改范围、验证命令和验收要求；并且已通过实际加载核查及至少一次适用的低风险流程验证。仅回复“我已遵守规范”不算验收通过。

**以后日常只需说：**「按当前项目规范完成 `TASK-xxx`，执行必要验证并交接。」

下面的内容是**自动接入时 Agent 的操作依据**，也供需要手动配置、排障或部署到团队/CI 的维护者使用；不是用户必须亲自执行的前置步骤。

## 二、理解原理：为什么不需要每次提醒 Agent

正常使用路径：

1. 把 **Vibecoding-Standard** 规范固定在本机可读取的位置（或放进项目的固定版本目录）。
2. 在**业务项目**已有的 `AGENTS.md` 中声明规范实际位置及本项目需求、任务、验证命令等**唯一真值源**。已有入口应增量合并，不覆盖。
3. Codex 读取项目 `AGENTS.md`；Claude Code 通过兼容的项目指令加载方式读取它。其他 Agent 通过实际支持的 Agent Harness / 启动提示显式加载。
4. 对新项目**实测一次**规范是否被正确加载、能否读取母规范、是否按任务约束与证据规则执行。
5. 日常直接给 Agent 派任务。**不要求每次重复输入一大段规范**。

注意：`AGENTS.md` 的**自动加载**不等于其中提及的所有 Markdown 一定被预加载；要在入口中明确指示 Agent **开始执行前读取母规范**，并以任务级核验确认其实际执行。仅把文件放在磁盘或写一个链接，都不能证明 Agent 遵守规则。

## 三、准备规范文件（两种方式二选一）

### 方式 A：单台 Windows 电脑使用一份本地规范（个人最简单）

示例位置：`F:\DOSS_Project\Vibecoding-Standard\`。在 PowerShell 中执行：

```powershell
git clone https://github.com/Abovetheclouds306/Vibecoding-Standard.git F:\DOSS_Project\Vibecoding-Standard
git -C F:\DOSS_Project\Vibecoding-Standard rev-parse HEAD
python F:\DOSS_Project\Vibecoding-Standard\tools\verify_manifest.py
python F:\DOSS_Project\Vibecoding-Standard\tools\check_links.py
```

- 将 `rev-parse HEAD` 输出的 **40 位 commit SHA** 记录在业务项目 `AGENTS.md` 或既有治理记录中，作为本项目采纳的规范版本身份。
- **不要求每次任务自动 `git pull`**，避免执行中途规则变化。需要完全锁定时，将规范工作副本保持在批准的 commit：`git -C F:\DOSS_Project\Vibecoding-Standard switch --detach <批准的完整 commit SHA>`。这一命令应在确认工作区没有待保留修改后执行。
- 本方式的绝对路径只对这台电脑有效；团队成员、Git worktree、CI 或异机使用时优先选下面方式 B。
- 私有仓库需要具有相应访问权的 GitHub 账号完成克隆。**不要把个人 Token 或凭据写入 AGENTS.md 或提交到业务仓库。**

### 方式 B：业务项目持有固定版本（团队 / 多 worktree / CI 推荐）

在目标业务仓库内使用固定相对位置，例如 `.vibecoding/standard/`：

```text
Nexus-Testing/
├── AGENTS.md
├── CLAUDE.md              # 使用 Claude Code 且需要时
├── .vibecoding/
│   └── standard/          # 固定版本的规范文件
│       ├── AI_PROJECT_STANDARD.md
│       ├── agents/
│       └── ...
├── framework/
└── tests/
```

可通过**带固定提交的 Git submodule**（团队都能访问私有仓库时）、或**经批准的规范快照**分发。两者均须保留来源仓库、版本、commit SHA 与校验结果。对无 GitHub 私有仓库访问权的 CI / 同事，使用经过授权的版本快照；不要假设 submodule 能匿名拉取。

此时业务项目 `AGENTS.md` 中引用 `.vibecoding/standard/AI_PROJECT_STANDARD.md`，而不是某一台电脑的绝对路径。规范升级属于独立受控变更；禁止任务进行中悄悄替换规范版本。

## 四、把规范接入业务项目的 `AGENTS.md`

**先检查项目已有文件与工作区**：是否已有根级 / 局部 `AGENTS.md`、`CLAUDE.md`、任务板、架构和测试命令、未提交修改。不要无差别覆盖；不要额外创建第二个 TODO 或 Task Board。需要完整模板时使用 [`../templates/AGENTS.md.template`](../templates/AGENTS.md.template)。

下面是**最小增量示例**（以方式 A 为例，内容须根据真实项目填写）：

```markdown
## 统一工程规范
- 标准：Vibecoding Standard v1.2.7 候选。
- 母规范：`F:\DOSS_Project\Vibecoding-Standard\AI_PROJECT_STANDARD.md`。
- 采纳的标准 commit：`<以 git rev-parse HEAD 实测的 40 位 SHA>`。
- 每次接受新任务，在修改代码前先实际读取母规范并确认适用条款；如无法读取，明确报告，禁止假称已遵守。
- 本项目需求 / Spec：`<项目既有权威路径>`。
- 本项目任务 / 状态：`<既有 Task Board 或唯一任务表路径>`。
- 测试与验证命令：`<实际可运行的命令或入口>`。
- 允许修改范围 / 实际环境及审批：`<真实边界>`。
- 执行与交接：按母规范的验证证据、DoD、并发保护与工作区卫生流程执行。
```

对于方式 B，仅把母规范路径换成仓库内相对路径 `.vibecoding/standard/AI_PROJECT_STANDARD.md`。保留业务仓库本来更严格的环境授权、删除保护和项目专属规则；通用规范**不取代**这些约束。

## 五、Agent 端分别怎么接入

### Codex

- 从**业务项目根目录**打开 Codex，使项目 `AGENTS.md` 处于它应读取的范围；注意当前工作目录和局部规则适用范围。
- 项目内的入口指向已锁定版本的母规范和当前业务真值源。日常无需指定 GitHub URL。
- 具体入口机制与推荐提示词详见 [`../agents/Codex.md`](../agents/Codex.md)。

### Claude Code

优先沿用已有 Claude Code 项目配置；必要时在业务项目根目录的 `CLAUDE.md` 中使用轻量显式导入：

```markdown
@AGENTS.md
```

- **已有 `CLAUDE.md` 时合并，不覆盖**；确认从 Claude Code 启动目录到父目录是否存在影响加载的指令文件。
- 或采用经验证有效的 `Project instructions` 双读取配置。加载行为受工具版本、实际配置和环境影响，**以 [`../agents/Claude-Code.md`](../agents/Claude-Code.md) 的机制和当前本机验证为准**。
- 可通过 Claude Code 的 `/context` 等当前支持的方式检查加载；需要进一步确定时采用内容敏感探针，不把 Agent 口头声称“我读了”单独视为强证据。

### Codem / 其他 Agent / 自定义 Harness

**不能假设它们自动读取 `AGENTS.md`、`CLAUDE.md` 或 GitHub 私有仓库。**

- 若 Agent 原生支持项目指令文件，就通过其官方机制设置入口。
- 若 Agent Harness 支持启动上下文 / 文件注入，应在启动时注入**业务项目入口及其所指的母规范**，且以任务实际所在工作区为准。
- 若不支持自动注入，首次任务以明确指令要求实际读取相关文件；是否需要每次提示取决于该 Agent 的会话与工作区加载机制。
- 先验证真实读取行为，再宣称“自动接入成功”；不得凭其他 Agent 的测试结论推断兼容。

此阶段**不需要为了读取规范而开发 MCP**。Skill 可在后续封装具体任务流程，不能替代常驻规范入口或验收门禁。

## 六、首次使用：验证接入真正生效

1. 在**新会话**启动 Agent，工作目录明确指向业务项目。
2. 请 Agent 指出：当前规范的**版本和实际文件路径**、项目唯一任务来源、允许修改范围、测试命令、完成时的证据与交接要求。
3. 核实结果确实来自项目入口及母规范；用命令、实际文件内容或工具提供的上下文检查辅助验证。必要时用**预先写入规则文件、不可猜的内容敏感口令**做隔离探针（不能让它靠随意搜索猜中）。
4. 选一项**离线、只读或低风险任务**，检查是否在开工前识别边界、真实运行允许的验证、正确区分 `PASS / FAIL / BLOCKED / NOT_RUN`、交付前从原始需求反向审查遗漏、检查临时探针去向并留存交接。
5. 记录 Agent 名称、版本、加载配置、规范 commit、业务工作区版本、任务 ID、实际观察与未测部分。只有实测通过，才称该组合已完成接入验证。

注意：`tools/verify_manifest.py` 验证的是**规范副本的文件完整性**，不是“Agent 自动加载成功”或“Agent 必然遵守规范”的证明。

## 七、日常使用与更新

一旦该项目接入并验证成功，通常只需说：

> 按项目 `AGENTS.md` 执行 `TASK-xxx`，在授权范围内完成必要验证、记录证据并交接。

日常不需要把整本规范塞进提示词，也无需每次先从 GitHub 远程拉取。新会话 / 更换 Agent / 更换工作目录 / 升级规范版本后，应重新检查入口和适用规则。

升级建议：在独立分支或 worktree 审核 GitHub 新版变更 → 确认项目映射与兼容性 → 更新固定版本和 commit SHA → 校验清单与链接 → 做至少一个小任务验收 → 按本项目授权流程合并。业务原有文件及他人未提交修改不得覆盖。

## 八、常见问题

| 现象 | 优先排查 |
| --- | --- |
| Agent 没读规范 | 当前项目目录是否正确？入口是否自动加载？外部规范文件能否访问？是否只写了路径没有要求读取？ |
| Claude Code 忽略 `AGENTS.md` | 检查 `CLAUDE.md` 与上层目录、`@AGENTS.md` 导入、`Project instructions` 配置及版本；按专项文档实测 |
| 只有一个人能访问私有规范仓库 | 采用经过授权的规范快照，或为相关人员配置适当权限；避免把 Token 写进业务代码 |
| Git worktree / CI 路径失效 | 使用项目内相对路径的固定版本方式 B，并检查 submodule 或快照是否已就绪 |
| Agent 声称遵守但行为不一致 | 比对真实文件、命令、验证证据与任务结果；文本规则不是独立的强制执行机制 |
| 规范升级后 MANIFEST 不通过 | 校验实际修改文件及其版本，按规范维护流程更新清单；不得在业务项目里随意重算权威发布清单 |

---

最重要的原则：**一次接入，让 Agent 找到规则；每次交付，用证据证明规则被实际执行。**
