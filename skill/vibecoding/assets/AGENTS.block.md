<!-- vibecoding:begin skill=0.1.0 standard=1.2.7 -->
## 工程纪律（Vibecoding v1.2.7）

本项目遵循 Vibecoding Standard v1.2.7。以下为不可省略的最低动作，细节见 `.vibecoding/` 与所用的 Agent Skill `vibecoding`。

- **唯一规则真值源**：`.vibecoding/vendor/vibecoding-standard/`（只读，与签收版本逐字节相同）。规则改动只能回到标准仓库发版，不得在此就地修改。
- **开工前**：读 `.vibecoding/config.json` 与 `.vibecoding/HANDOFF.md`；确认分支、HEAD 与工作区状态。
- **验证纪律**：结论必须附命令与**实际退出码**。`0=PASS / 1=FAIL / 2=UNKNOWN`；`2` 既不得当通过，也不得当"跳过"。
- **禁止假 PASS**：未运行写 `NOT_RUN`；为了让门禁变绿而放宽测试断言属禁止行为。
- **证据**：一任务一份 `.vibecoding/evidence/<TASK>.md`，含命令、退出码、证据路径、复查条件。
- **交接**：会话中断前更新 `.vibecoding/HANDOFF.md`；新会话先读它再动手。
- **不改他人改动**：不 `reset` / `checkout --` / `clean` / 强推；发现无关改动保留并报告。
<!-- vibecoding:end -->
