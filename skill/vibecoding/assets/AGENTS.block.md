<!-- vibecoding:begin skill=0.1.0 standard=1.2.7 -->
## 工程纪律（Vibecoding v1.2.7）

本项目遵循 Vibecoding Standard v1.2.7。以下为不可省略的最低动作，细节见 `.vibecoding/` 与所用的 Agent Skill `vibecoding`。

- **唯一规则真值源**：Vibecoding Standard v1.2.7 正文，只读，与签收版本逐字节相同。规则改动只能回到标准仓库发版，不得就地修改。
  - **规范位置**：以 `.vibecoding/config.json` 的 `standard_vendor_path` 字段为准；该目录须含 `AI_PROJECT_STANDARD.md` 与 `MANIFEST.sha256`。
  - **本次初始化解算**：`.claude/skills/vibecoding/vendor/vibecoding-standard`（项目内相对路径，随项目整体移动仍有效；技能被卸载则该路径消失）。
  - **路径不可读时**：说明技能已卸载或项目已移动。此时**不得假装规范已加载**，也不得引用未读到的条款；须重新安装技能后执行 `vb_init.py --project . --apply` 重定位。
- **开工前**：读 `.vibecoding/config.json` 与 `.vibecoding/HANDOFF.md`；确认分支、HEAD 与工作区状态。
- **验证纪律**：结论必须附命令与**实际退出码**。`0=PASS / 1=FAIL / 2=UNKNOWN`；`2` 既不得当通过，也不得当"跳过"。
- **禁止假 PASS**：未运行写 `NOT_RUN`；为了让门禁变绿而放宽测试断言属禁止行为。
- **证据**：一任务一份 `.vibecoding/evidence/<TASK>.md`，含命令、退出码、证据路径、复查条件。
- **交接**：会话中断前更新 `.vibecoding/HANDOFF.md`；新会话先读它再动手。
- **不改他人改动**：不 `reset` / `checkout --` / `clean` / 强推；发现无关改动保留并报告。
<!-- vibecoding:end -->
