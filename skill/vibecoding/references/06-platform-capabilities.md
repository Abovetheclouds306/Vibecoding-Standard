# 06 · 平台能力与限制（截至 2026-10-25）

> **证据分级**：`OFFICIAL_DOCUMENTED`＝官方文档写明；`LOCALLY_VERIFIED`＝本机实测；`VERSION_DEPENDENT`＝随版本变化；`UNVERIFIED`＝无可靠依据；`NOT_RUN`＝未执行。
> **不要把理论兼容当实测通过。** 本文件里凡标 `OFFICIAL_DOCUMENTED` 的，只说明"文档这么写"，不等于"本机这个版本真的这么跑"。

## 一、开放格式（四家共用）

| 项 | 要求 | 级别 |
| --- | --- | --- |
| 结构 | 目录 + `SKILL.md`（必需）；`scripts/`、`references/`、`assets/` 可选 | OFFICIAL_DOCUMENTED |
| `name` | ≤64 字符，小写字母/数字/连字符，不得首尾连字符或连续连字符，**必须与父目录同名** | OFFICIAL_DOCUMENTED |
| `description` | ≤1024 字符，写清"做什么"和"何时用" | OFFICIAL_DOCUMENTED |
| 可选字段 | `license`、`compatibility`、`metadata`、`allowed-tools`（实验性） | OFFICIAL_DOCUMENTED |
| 加载方式 | 渐进披露：元数据常驻 → 激活时读 `SKILL.md` → 资源按需 | OFFICIAL_DOCUMENTED |
| 建议体量 | `SKILL.md` < 500 行 | OFFICIAL_DOCUMENTED |

## 二、四平台能力矩阵

| 能力 | Claude Code | Codex | Cursor | WorkBuddy |
| --- | --- | --- | --- | --- |
| 读 `SKILL.md` | ✅ | ✅ | ✅ | ✅ |
| 项目级目录 | `.claude/skills/` | `.agents/skills/`（从 CWD 逐级向上到仓库根） | `.cursor/skills/`、`.agents/skills/`（递归，含嵌套子目录） | 文档写 `.codebuddy/skills/`；**本机另有 `~/.workbuddy/skills/`** |
| 用户级目录 | `~/.claude/skills/` | `$HOME/.agents/skills/` | `~/.cursor/skills/`、`~/.agents/skills/` | 文档写 `~/.codebuddy/skills/`；本机 `~/.workbuddy/skills/` 也存在 |
| **自动发现**（不点名就出现在列表） | ✅ 启动时加载 name+description | ✅ 启动时扫描，初始列表有预算上限 | ✅ 自动加载 | ✅ |
| **自动激活**（按 description 匹配任务） | ✅ 默认开启 | ✅ 隐式调用 | ✅（按描述相关时应用） | ✅（"AI 根据任务自动选择"） |
| **显式调用** | `/skill-name`（须在消息开头） | `/skills` 或 `$skill-name` | `/skill-name` 或 `@skill-name` | `/skill-name` |
| **禁止模型自动调用** | `disable-model-invocation: true` | 需 `agents/openai.yaml` 策略（见下） | 未查到等价字段 | `disable-model-invocation: true` |
| **按文件范围限定** | `paths`（glob） | 未查到 | `paths`（glob 或逗号分隔） | 未查到 |
| **技能级 Hooks** | `hooks` 字段（技能调用时注册） | 未查到 | 未查到 | `hooks` 仅 `context: fork` 时生效 |
| 冲突解析 | 企业 > 个人 > 项目 | 同名不合并，都可出现 | 未描述 | 未描述 |
| 描述截断 | `description` + `when_to_use` 合计截断 1536 字符 | 初始列表 ≤2% 上下文或 8000 字符，先压缩描述 | 未描述 | 未描述 |

**Codex 的 `allow_implicit_invocation: false`**：见于第三方文章（`agents/openai.yaml` 的 `policy`），**官方页面未确认** → 标 `UNVERIFIED`，本 POC 不使用该配置。

## 三、本机实测状态（2026-10-25）

| 平台 | 本机可用性 | 本 POC 做了什么 | 结论级别 |
| --- | --- | --- | --- |
| Claude Code | `claude 2.1.303` 可用；`~/.claude/skills/` 存在（25 项） | 在隔离示例项目装项目级技能，跑真实 `claude -p` 观察是否自动激活 | 见 POC 报告 §自动激活证据 |
| Codex | `codex` 可执行（版本命令有告警输出） | 目录结构兼容性检查；真实激活尝试结果见报告 | 见 POC 报告 |
| Cursor | **无 `cursor-agent` CLI**，本机无 `~/.cursor/skills/` | 仅做目录/字段级静态核对 | 自动激活 **NOT_RUN** |
| WorkBuddy | 当前会话宿主；`~/.workbuddy/skills/` 与 `~/.codebuddy/skills/` 均存在 | 项目级安装 + 结构核对；会话内无法热加载新技能 | 真实激活 **NOT_RUN**（需新会话） |

## 四、路径口径分歧（WorkBuddy）

同一家文档给出两个用户级路径：

- `workbuddy.cn/docs/ide/Features/Skills`：工作区 `.codebuddy/skills/`
- `workbuddy.ai/docs/cli/skills`：项目 `.codebuddy/skills/`、用户 `~/.codebuddy/skills/`
- 平台内置的 `skill-creator` 指引：`~/.workbuddy/skills/`、`.workbuddy/skills/`

本机两个目录都存在，**无法在单会话内判定宿主实际扫描哪个** → `NOT_RUN`。
**POC 的做法**：安装脚本同时支持 `--target` 显式指定，并在两个候选路径各放一份（可 `--dry-run` 预览），把"猜路径"变成"显式参数"。

## 五、必须向用户明说的限制

1. **装上不等于生效**：自动激活依赖宿主的 description 匹配，可能失败（描述被截断、技能太多被省略、模型判断偏差）。
2. **装上不等于遵循**：模型可能激活了技能却不执行其中步骤。唯一可靠的一层是确定性脚本 / CI。
3. **不支持无人值守**：本技能不提供守护进程、不轮询、不自动提交。
4. **平台差异是真实成本**：同一份 `SKILL.md` 在四家的目录不同、扩展字段不同；`allowed-tools`、`hooks`、`paths` 各有着落差异。
5. **装载时机**：Codex 会自动检测变更（未生效则重启）；WorkBuddy 类宿主在会话启动时注入技能列表，**会话内新增技能不会被当前会话看到**。

## 六、选型建议（POC 结论）

| 目标 | 建议 |
| --- | --- |
| 一份包覆盖多家 | 只依赖标准字段（`name`/`description`/`license`/`compatibility`/`metadata`），平台专有字段一律不用 |
| 需要"绝不自动跑"的技能 | 加 `disable-model-invocation: true`（Claude Code / WorkBuddy 支持；Codex 待验证） |
| 需要真正挡住假 PASS | 别指望技能，把 `vb_gate.py` 放进 CI 或 pre-commit |
| 项目需要跨 Agent 最低纪律 | 用 `AGENTS.md` 标记块（第 1 层），技能只是第 2 层的增强 |
