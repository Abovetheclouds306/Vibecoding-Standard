# TODO（skill/ 任务真相源）

状态取值：PASS（开发者自测）/ FAIL / UNKNOWN / NOT_RUN / OPEN。自测 PASS 不等于 R4 复核通过。

| ID | 事项 | 状态 | 说明 |
|---|---|---|---|
| INS-1 | install_skill.py `--force` 会 rmtree 删除未知内容 | 自测 PASS | 95d41bf；归属清单 + 冲突拒绝 + 链接/边界；待 R4 |
| CLI-1 | `--json` 失败路径输出契约 JSON（status/error/rc） | 自测 PASS | 60a4ed1 |
| CLI-2 | `--update-block` 状态与 rc 一致 | 自测 PASS | 原实现已正确，补测试；JSON 增加 status |
| CLI-3 | assets/AGENTS.block.md 与 BLOCK 渲染防漂移 | 自测 PASS | 原实现一致，补测试 |
| CLI-4 | vendor 定位与项目搬迁 | 自测 PASS | 原实现正确，补测试 |
| CLI-5 | 技能缺失如实报告 | 自测 PASS | 修复：显式 `--standard` 无效时原先静默回退到其他副本 |
| CLI-6 | init / 安装器幂等 | 自测 PASS | 补测试 |
| LNK-F | 文件级符号链接用例 | NOT_RUN | 本机无创建文件符号链接权限（需开发者模式/管理员）；目录 Junction 用例已运行 |
| R4-N1 | 安装器：普通文件占据所需目录位置，--force 下仍部分写入后 rc1 | 自测 PASS | a887cd9；预检判为冲突 rc2、零写入（含 --force）；待 R5 复核 |
| R4-N2 | vb_init `_compensate` 无归属判据，项目内 Junction 重定向导致误删 | 自测 PASS | 9c91a9e；仅当前内容==本进程写入值才还原/删除，否则记残留；新建目录登记 baseline 并在父路径校验；回滚跳过项一律进残留，不再宣称“已回滚” |
| R4-N3 | 安装器：内层链接分量 rc2（文档写 rc1） | 自测 PASS | a887cd9；平凡的退出码对齐：链接/越界 → REFUSED rc1；测试断言收紧为 rc==1 |
| R4-N4 | 安装器：dest 上层分量为 Junction 时跟随写出项目外 | 自测 PASS | 6a0d17a；project scope 下项目根（不含）→dest 各分量为链接 → REFUSED rc1；user scope 的 ~ 及其上层不检查（测试禁止触碰 ~，NOT_RUN） |
| R4-N5 | 安装器：未检查 dest 与 source 重叠 | 自测 PASS | 56c60fe；realpath 相同或互相包含 → REFUSED rc1，零写入 |
| R4-N6 | vb_init `--json` 包装层按字面匹配 argv（缩写/等号写法） | 部分修复 / 余项待 Owner 决定 | d2a83c3；allow_abbrev=False（--jso/--app 为用法错误 rc2），JSON 兜底的 mode/project 改为解析推导（支持 --project=X）。待 Owner 决定：`--json --help` 的 status（当前 usage_error rc0）与 KeyboardInterrupt 的 JSON 输出——改动属于 --json 状态契约变更 |
| R4-N7 | `--standard` / VB_STANDARD_HOME 可指向任意自校验目录 | DEFERRED（待 Owner 决定） | 修复需固定 MANIFEST 哈希，改变 --standard 契约并新增功能，超出本轮授权 |
| R4-N8 | c08407d 残留报告描述不准确 | 自测 PASS | 691f4dc；补偿先 guard 后读，guard 失败不经被替换路径读取/描述，也不再宣称「本次未改动」 |
| R4-N9 | 项目位于盘符根目录时写入全被拒 | 自测 PASS | 608118c；`_inside` 根安全（根已以分隔符结尾时不再拼接），preflight 复用 |
| R4-N10 | 测试与清单的小缺口（清单中 ../、绝对路径键被保留等） | 自测 PASS + DOCS | ace30ec；合并时丢弃非法清单键；新增内层 Junction 指向 dest 内用例（杀 M2）。DOCS：清单无签名/认证，仅作归属记录，伪造匹配哈希可让文件被视为「本工具所有」 |
| R5-N1 | 安装器：dest 本身或其上层被普通文件占据时未进预检冲突（执行阶段异常 rc1，零写入） | 自测 PASS | 1900fd9；dest 及其不存在的上层位置被非目录占用 → 预检冲突 rc2，零写入（含 --force、默认 .claude 布局） |
| R5-N2 | R4-N2 核心机制缺测试保护 | 自测 PASS | a1a32c8；M4–M7 均 KILLED；待 R6 复核 |
| R5-N3 | 补偿阶段残留未在回滚后核对，描述可能与事实相反（R4-N8 延伸） | 自测 PASS（R8 修正） | 691f4dc 的撤销逻辑被 R7 判为回归（R7-N1）；368f20a：补偿时路径被重定向的残留不再撤销，只在回滚后更新描述（原路径已收敛、实际落点未知）；未被重定向的残留在回滚确认收敛后才撤销 |
| R5-N4 | 安装器 TOCTOU：预检后出现的占位文件 | DOCS | 「零写入」仅是预检层保证；预检与写入之间并发出现的占位仍可能导致执行阶段失败（rc1），不引入事务框架 |
| R5-N5 | HANDOFF §9 skip 计数不准 | 已更正 | skip 数随仓库所在盘而变：F: worktree 为 1，与 %TEMP% 同盘为 2 |
| R6-N1 | 开发者临时目录名与复核者冲突（vbr6/vbR6） | 已更正（流程） | R7 起开发专用目录 %TEMP%\vbdev_r7 |
| R6-N2 | M7 保护只有一个文本模式用例 | 自测 PASS | 337aef1；新增 --json 变体与「预先存在文件被他人改动」变体，M7 下两例均 FAIL |
| R7-N1 | 回滚按当前路径收敛撤销残留，掩盖经 Junction 写出项目外的覆盖（R5-N3 回归） | 自测 PASS | 368f20a；被重定向条目保留 ResidualRisk，不再输出「FAILED（已回滚」 |
| R7-N2 | R4-N4 检查用 startswith("..")，`..x` 分量可绕过 | 自测 PASS | fb53917；按首个路径分量判断是否越出项目 |
| R7-N3 | 文档过度承诺「任一层链接 → rc1」 | DOCS | 130753c；docstring 与 HANDOFF §3 写明不检查 user scope 的 ~ 上层、绝对/越出项目 --path 的上层 |
| R7-N4 | preflight 盘符根改动无测试保护（变异 E2 存活） | 自测 PASS | 41bb45e；只读调用 preflight(盘符根)，无越界误报；E2 KILLED |
| R7-N5 | 清单非法键只在重写清单时丢弃；Windows 别名键（NUL、尾点/空格、大小写）可通过过滤 | OPEN（Info） | 无变化时为丢键而重写清单会改变「无变化零写入」语义；别名键归属按源 rel 精确匹配，暂无实际影响 |
| R7-N6 | 项目外悬空 Junction 作上层被归为非目录占用 rc2 | 自测 PASS | 2289ccc；悬空链接按链接 REFUSED rc1，零写入 |
| R4-N6 余项 | `--json --help` status / KeyboardInterrupt | DEFERRED（待 Owner 决定） | R7 认为 status ok 在现有枚举内，但仍属行为契约选择，不改 |
| R4-c08407d | 对 c08407d（及本分支）的独立复核 | 已完成 R4 | R4-REPORT.md：PASS-with-findings；R5 复核 5327eb9..HEAD 待安排 |
| VENDOR-SCOPE | vendor 范围决策（全量 vendored 还是精简） | OPEN | 需 Chris 决定 |
| POC-PUSH | poc/vibecoding-skill-v0.1.0 与本 fix 分支均未推送远程 | OPEN | 推送需 Chris 明确批准 |
