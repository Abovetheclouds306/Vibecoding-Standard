#!/usr/bin/env python3
"""vb_init.py — Vibecoding Skill 受保护初始化（PbC：默认 dry-run，--apply 才落盘）。

约束（与 SKILL.md 铁律一致）：
1. 从不编辑 CLAUDE.md；从不改写 AGENTS.md 标记块之外的内容。
2. 重复执行必须幂等：第二次全部 unchanged，不新增/不改动任何文件。
3. 写入 tracked 文件前若工作区脏，需 --allow-dirty。
4. 标准副本校验不过则拒绝初始化（退出码 1），不写任何文件。
5. 写盘前做可预见检查（目标类型冲突、路径不得越出项目目录）；任何检查不过即拒绝，且尚未写任何文件。
6. 所有写盘经 WriteJournal 登记：可控异常按逆序回滚本次写入（只回滚本进程创建/修改、
   且当前内容仍等于本进程写入值的文件；不删除用户原有文件），失败返回非零退出码并打印诊断。
   **边界**：进程被强杀（SIGKILL）、断电、文件系统故障等无法捕获的终止不在回滚范围内，
   因此不做跨文件原子提交，也不宣称"任何异常都零残留"。

退出码：0 = 成功/无需变更；1 = 拒绝或出错（含已回滚的失败）；2 = 需要人工决定（块内容 differs）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

SKILL_VERSION = "0.1.0"
STANDARD_VERSION = "1.2.7"
STANDARD_SIGNOFF = "ce5b361cf13ae373094abe67eb9ce7a6e22ecb8f"
STANDARD_RELEASE = "fd9750f3e6c4c2105cf253d5f7d6494f0f373fdf"
STANDARD_ZIP_SHA = "0ce2a06cf506904cca4e0597240d43f5e869ee9845d7b508bc83a9fd2745dd38"

BEGIN = "<!-- vibecoding:begin"
END = "<!-- vibecoding:end -->"

BLOCK = """<!-- vibecoding:begin skill={sv} standard={std} -->
## 工程纪律（Vibecoding v{std}）

本项目遵循 Vibecoding Standard v{std}。以下为不可省略的最低动作，细节见 `.vibecoding/` 与所用的 Agent Skill `vibecoding`。

- **唯一规则真值源**：`.vibecoding/vendor/vibecoding-standard/`（只读，与签收版本逐字节相同）。规则改动只能回到标准仓库发版，不得在此就地修改。
- **开工前**：读 `.vibecoding/config.json` 与 `.vibecoding/HANDOFF.md`；确认分支、HEAD 与工作区状态。
- **验证纪律**：结论必须附命令与**实际退出码**。`0=PASS / 1=FAIL / 2=UNKNOWN`；`2` 既不得当通过，也不得当"跳过"。
- **禁止假 PASS**：未运行写 `NOT_RUN`；为了让门禁变绿而放宽测试断言属禁止行为。
- **证据**：一任务一份 `.vibecoding/evidence/<TASK>.md`，含命令、退出码、证据路径、复查条件。
- **交接**：会话中断前更新 `.vibecoding/HANDOFF.md`；新会话先读它再动手。
- **不改他人改动**：不 `reset` / `checkout --` / `clean` / 强推；发现无关改动保留并报告。
<!-- vibecoding:end -->
"""

HANDOFF_TEMPLATE = """<!-- generated-by: vb_handoff v{sv} -->
# {task} 交接

Updated: {ts}
Task source: 见项目自身任务系统（本文件不复制任务状态）
Workspace: {workspace}
Baseline: {baseline}

## 已完成
{summary}

## 验证
{verify}

## 未完成与阻塞
{blocked}

## 已发生的外部效果
{effects}

## 工作区卫生
{hygiene}

## 恢复步骤
1. `git status --porcelain` 确认未提交改动归属。
2. 读 `.vibecoding/evidence/` 下与本任务相关的证据，核对结论与退出码。
3. 按"未完成与阻塞"逐项继续，不重跑已有副作用的步骤。

## 下一步
{next}
"""

EVIDENCE_TEMPLATE = """<!-- generated-by: vb_gate v{sv} -->
# {task} 验证记录

Task: {task}
Time: {ts}
Baseline: {baseline}
Environment: {env}

| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | <待执行> | NOT_RUN | NOT_RUN | N/A | 由 vb_gate.py 首次运行时生成 |

结论：NOT_RUN
反向遗漏审查：待人工填写（本任务范围、确认的遗漏与处置）
审查：待人工填写（审查者、版本、结论）
Artifacts: N/A
Recheck Conditions: 代码、依赖或测试变更后需重跑
Cleanup / Recovery: N/A
Release Status: 未涉及
"""


def run(args: list[str], cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, shell=False)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", "command not found: %s" % args[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout: %s" % " ".join(args)


def git(project: str, *args: str) -> tuple[int, str]:
    rc, out, err = run(["git", *args], cwd=project)
    return rc, (out if rc == 0 else err).strip()


def git_state(project: str) -> dict:
    rc, top = git(project, "rev-parse", "--show-toplevel")
    if rc != 0:
        return {"is_repo": False, "root": None, "head": None, "branch": None, "dirty": None, "porcelain": ""}
    _, head = git(project, "rev-parse", "HEAD")
    _, branch = git(project, "rev-parse", "--abbrev-ref", "HEAD")
    _, status = git(project, "status", "--porcelain")
    return {
        "is_repo": True,
        "root": top,
        "head": head,
        "branch": branch,
        "dirty": bool(status),
        "porcelain": status,
    }


def detect_eol(path: str) -> bytes:
    """返回该文件应使用的换行序列：以文件自身为准，避免混行尾。"""
    try:
        data = _read_raw(path)
    except OSError:
        return b"\n"
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    return b"\r\n" if crlf > lf else b"\n"


def _write_raw(path: str, data: bytes) -> None:
    """唯一写盘出口（单测可替换以注入可控异常）。"""
    with open(path, "wb") as fh:
        fh.write(data)


def _read_raw(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class WriteJournal:
    """记录本次运行的文件写入，异常时按逆序回滚。

    回滚边界（如实声明）：
    - 只回滚**本进程**创建或修改、且**当前内容仍等于本进程写入值**的文件；
      若发现内容已被其他进程改动，则保留现状并标注 skipped-modified（不覆盖他人改动）。
    - 只删除**本进程新建且回滚时为空**的目录。
    - `SIGKILL` / 断电等无法捕获的终止不在覆盖范围（不做跨文件原子提交）。
    """

    def __init__(self) -> None:
        self.entries: list[dict] = []
        self.created_dirs: list[str] = []
        self.step = "初始化"

    def mkdir(self, path: str) -> None:
        """递归创建目录，并记录本进程新建的层级（用于回滚时清理）。"""
        if os.path.isdir(path):
            return
        missing = []
        cur = os.path.abspath(path)
        while not os.path.isdir(cur):
            missing.append(cur)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        os.makedirs(path, exist_ok=True)
        self.created_dirs.extend(missing)

    def write(self, path: str, data: bytes, step: str = "") -> None:
        existed = os.path.exists(path)
        original = _read_raw(path) if existed else None
        try:
            _write_raw(path, data)
        except Exception:
            # 本条写入自身失败：就地自愈（恢复原内容 / 删除半成品），再交给上层统一回滚
            try:
                if existed:
                    _write_raw(path, original)
                elif os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
            raise
        self.entries.append({
            "path": path, "existed": existed, "original": original,
            "written": data, "step": step or self.step,
        })

    def rollback(self) -> list[str]:
        actions: list[str] = []
        for e in reversed(self.entries):
            path = e["path"]
            try:
                cur = _read_raw(path) if os.path.exists(path) else None
            except OSError as exc:  # 读不回就不动它
                actions.append("Skipped(unreadable) %s (%s)" % (path, exc))
                continue
            if cur == e["written"]:
                try:
                    if e["existed"]:
                        _write_raw(path, e["original"])
                        actions.append("Restored %s" % path)
                    else:
                        os.remove(path)
                        actions.append("Removed %s" % path)
                except OSError as exc:
                    actions.append("Failed %s (%s)" % (path, exc))
            else:
                actions.append("Skipped(modified-by-others) %s" % path)
        for d in reversed(self.created_dirs):
            try:
                os.rmdir(d)
                actions.append("RemovedDir %s" % d)
            except OSError:
                pass  # 非空或已不存在：保留
        return actions


def preflight(project: str, plan: dict) -> list[str]:
    """写入前的可预见问题检查；返回问题列表（非空即拒绝执行，且尚未写任何文件）。"""
    problems: list[str] = []
    if not os.path.isdir(project):
        return ["项目目录不存在或不是目录: %s" % project]
    root = os.path.realpath(project)

    def inside(p: str) -> bool:
        rp = os.path.realpath(p)
        return rp == root or rp.startswith(root + os.sep)

    targets = ["AGENTS.md", ".vibecoding", ".vibecoding/config.json",
               ".vibecoding/AGENTS.block.md", ".vibecoding/evidence",
               ".vibecoding/evidence/_template.md", ".vibecoding/HANDOFF.md"]
    for rel in targets:
        p = os.path.join(project, rel)
        if not inside(p):
            problems.append("目标路径越出项目目录（拒绝写入）: %s" % p)

    vb = os.path.join(project, ".vibecoding")
    ev = os.path.join(project, ".vibecoding", "evidence")
    agents = os.path.join(project, "AGENTS.md")
    if plan.get("status") == "conflict":
        problems.append(plan.get("detail") or "AGENTS.md 目标类型冲突")
    if os.path.exists(vb) and not os.path.isdir(vb):
        problems.append(".vibecoding 已存在但不是目录: %s" % vb)
    if os.path.exists(ev) and not os.path.isdir(ev):
        problems.append(".vibecoding/evidence 已存在但不是目录: %s" % ev)
    if plan.get("status") != "created" and os.path.isdir(agents) and plan.get("status") != "conflict":
        problems.append("AGENTS.md 是目录，无法作为文件写入: %s" % agents)
    if not os.access(project, os.W_OK):
        problems.append("项目目录不可写: %s" % project)
    return problems


def find_standard(project: str, explicit: str | None) -> tuple[str | None, str]:
    """定位标准副本目录（含 tools/verify_manifest.py 的目录）。返回 (路径, 来源说明)。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates: list[tuple[str, str]] = []
    if explicit:
        candidates.append((explicit, "--standard 参数"))
    env = os.environ.get("VB_STANDARD_HOME")
    if env:
        candidates.append((env, "环境变量 VB_STANDARD_HOME"))
    candidates.append((os.path.normpath(os.path.join(here, "..", "vendor", "vibecoding-standard")), "技能内置 vendor"))
    project_vendor = os.path.join(project, ".vibecoding", "vendor", "vibecoding-standard")
    candidates.append((project_vendor, "项目内 .vibecoding/vendor"))

    for path, source in candidates:
        if path and os.path.isfile(os.path.join(path, "tools", "verify_manifest.py")):
            return os.path.abspath(path), source
    return None, "未找到（检查 --standard / VB_STANDARD_HOME / vendor 目录）"


def verify_standard(standard: str, python_exe: str) -> tuple[int, list[str]]:
    rc, out, err = run([python_exe, os.path.join(standard, "tools", "verify_manifest.py")], cwd=standard, timeout=300)
    tail = [l for l in (out + err).strip().splitlines() if l.strip()][-6:]
    return rc, tail


def split_block(text: str) -> tuple[int, int] | None:
    """返回标记块的 (start, end) 字节偏移（字符索引），无块返回 None。"""
    i = text.find(BEGIN)
    if i < 0:
        return None
    j = text.find(END, i)
    if j < 0:
        return None
    return i, j + len(END)


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def plan_agents(project: str, desired_block: str) -> dict:
    path = os.path.join(project, "AGENTS.md")
    if not os.path.exists(path):
        return {"file": "AGENTS.md", "status": "created", "detail": "不存在，将创建并写入标记块", "path": path}
    if os.path.isdir(path):
        return {"file": "AGENTS.md", "status": "conflict",
                "detail": "AGENTS.md 是目录，无法作为文件读写: %s" % path, "path": path}
    raw = _read_raw(path)
    text = raw.decode("utf-8", "replace")
    span = split_block(text)
    if span is None:
        return {"file": "AGENTS.md", "status": "appended", "detail": "存在且无标记块，将在文件末尾追加（原有内容不动）", "path": path}
    existing = text[span[0]:span[1]]
    if normalize(existing) == normalize(desired_block):
        return {"file": "AGENTS.md", "status": "unchanged", "detail": "标记块已存在且一致（幂等）", "path": path}
    return {"file": "AGENTS.md", "status": "differs", "detail": "标记块存在但内容不同，需 --update-block 才更新", "path": path}


def apply_agents(plan: dict, desired_block: str, update_block: bool, project: str,
                 journal: WriteJournal) -> str:
    path = plan["path"]
    if plan["status"] in ("unchanged", "differs"):
        if plan["status"] == "differs":
            if not update_block:
                return "skipped(需 --update-block)"
            raw = _read_raw(path)
            text = raw.decode("utf-8", "replace")
            span = split_block(text)
            eol = "\r\n" if detect_eol(path) == b"\r\n" else "\n"
            new = text[:span[0]] + desired_block.replace("\n", eol).rstrip("\r\n") + text[span[1]:]
            journal.write(path, new.encode("utf-8"), step="AGENTS.md 更新标记块")
            return "block_updated"
        return "no_change"

    eol_bytes = detect_eol(path) if os.path.exists(path) else b"\n"
    block_bytes = desired_block.replace("\n", eol_bytes.decode()).rstrip("\r\n").encode("utf-8")

    if plan["status"] == "created":
        journal.write(path, block_bytes + eol_bytes, step="AGENTS.md 创建")
        return "created"

    existing = _read_raw(path)
    payload = bytearray(existing)
    if existing and not existing.endswith(b"\n"):
        payload += eol_bytes
    payload += eol_bytes
    payload += block_bytes
    payload += eol_bytes
    journal.write(path, bytes(payload), step="AGENTS.md 追加标记块")
    return "appended"


def write_if_changed(path: str, content: bytes, journal: WriteJournal | None = None) -> str:
    if os.path.exists(path):
        if _read_raw(path) == content:
            return "unchanged"
        return "differs"
    if journal is not None:
        journal.mkdir(os.path.dirname(path))
        journal.write(path, content, step="写入 %s" % os.path.basename(path))
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_raw(path, content)
    return "created"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Vibecoding Skill 受保护初始化（默认 dry-run）")
    ap.add_argument("--project", default=".", help="目标项目目录（默认当前目录）")
    ap.add_argument("--standard", help="标准副本目录（含 tools/verify_manifest.py）")
    ap.add_argument("--apply", action="store_true", help="实际落盘；缺省为 dry-run")
    ap.add_argument("--allow-dirty", action="store_true", help="工作区脏时仍允许改 tracked 文件")
    ap.add_argument("--update-block", action="store_true", help="标记块内容不同时允许覆盖")
    ap.add_argument("--skip-standard-check", action="store_true", help="跳过标准副本完整性校验（不推荐）")
    ap.add_argument("--python", default=sys.executable, help="用于调用标准工具的解释器")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print("ERROR: 项目目录不存在: %s" % project)
        return 1

    result: dict = {"project": project, "mode": "apply" if args.apply else "dry-run", "steps": [], "rc": 0}

    standard, source = find_standard(project, args.standard)
    if not standard:
        print("REFUSED: 未找到标准副本。%s" % source)
        return 1
    result["standard"] = {"path": standard, "source": source}

    if not args.skip_standard_check:
        rc, tail = verify_standard(standard, args.python)
        result["standard"]["verify_rc"] = rc
        result["standard"]["verify_tail"] = tail
        if rc != 0:
            print("REFUSED: 标准副本完整性校验未通过（退出码 %d），未写入任何文件。" % rc)
            for line in tail:
                print("  " + line)
            return 1
    else:
        result["standard"]["verify_rc"] = None
        result["standard"]["verify_tail"] = ["skipped"]

    state = git_state(project)
    result["git"] = {k: state[k] for k in ("is_repo", "root", "head", "branch", "dirty")}

    desired_block = BLOCK.format(sv=SKILL_VERSION, std=STANDARD_VERSION)
    plan = plan_agents(project, desired_block)

    touch_tracked = plan["status"] in ("appended", "differs") or (plan["status"] == "created" and state["is_repo"])
    if args.apply and state["dirty"] and touch_tracked and not args.allow_dirty:
        print("REFUSED: 工作区有未提交改动，且本次会修改 AGENTS.md。确认无冲突后加 --allow-dirty。")
        print(state["porcelain"] or "(status 为空但 dirty 判定为真)")
        return 1

    journal = WriteJournal()
    state_cfg = "would_write"
    state_block = "would_write"
    state_ev = "would_write"
    state_ho = "exists(unchanged)" if os.path.exists(os.path.join(project, ".vibecoding", "HANDOFF.md")) else "would_create"

    if not args.apply:
        plan["action"] = "would_" + plan["status"]
        result["steps"].append(plan)
        result["steps"].append({"file": ".vibecoding/config.json", "status": state_cfg})
        result["steps"].append({"file": ".vibecoding/AGENTS.block.md", "status": state_block})
        result["steps"].append({"file": ".vibecoding/evidence/_template.md", "status": state_ev})
        result["steps"].append({"file": ".vibecoding/HANDOFF.md", "status": state_ho})
    else:
        problems = preflight(project, plan)
        if problems:
            print("REFUSED: 写入前检查未通过（未写入任何文件）。")
            for p in problems:
                print("  - " + p)
            return 1

        # 跨盘符（Windows 不同 mount）无法相对化：退化为绝对路径，避免 ValueError 崩溃
        try:
            vendor_rel = os.path.relpath(standard, project).replace("\\", "/")
        except ValueError:
            vendor_rel = os.path.abspath(standard).replace("\\", "/")

        manifest = {
            "skill_version": SKILL_VERSION,
            "standard_version": STANDARD_VERSION,
            "standard_signoff_commit": STANDARD_SIGNOFF,
            "standard_release_commit": STANDARD_RELEASE,
            "standard_vendor_zip_sha256": STANDARD_ZIP_SHA,
            "standard_vendor_path": vendor_rel,
            "initialized_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        }
        cfg_path = os.path.join(project, ".vibecoding", "config.json")
        try:
            # 1) 先建目录：这是 F-1 的根因修复点（原先直接写 config.json 导致 FileNotFoundError）
            journal.step = "创建 .vibecoding/ 目录"
            journal.mkdir(os.path.join(project, ".vibecoding"))
            journal.mkdir(os.path.join(project, ".vibecoding", "evidence"))

            # 2) config.json（幂等：只比稳定字段，initialized_at 保留原值）
            journal.step = ".vibecoding/config.json"
            stable = ("skill_version", "standard_version", "standard_signoff_commit",
                      "standard_release_commit", "standard_vendor_zip_sha256", "standard_vendor_path")
            prev = None
            if os.path.exists(cfg_path):
                try:
                    prev = json.loads(_read_raw(cfg_path).decode("utf-8"))
                except (json.JSONDecodeError, OSError):
                    prev = None
            cfg_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if prev is not None and all(prev.get(k) == manifest.get(k) for k in stable):
                state_cfg = "unchanged"
            elif prev is not None:
                manifest["initialized_at"] = prev.get("initialized_at") or manifest["initialized_at"]
                cfg_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                journal.write(cfg_path, cfg_bytes, step=".vibecoding/config.json 更新")
                state_cfg = "updated"
            else:
                journal.write(cfg_path, cfg_bytes, step=".vibecoding/config.json 创建")
                state_cfg = "created"

            # 3) AGENTS.block.md 副本（存在且不同则不动，保持原语义）
            journal.step = ".vibecoding/AGENTS.block.md"
            state_block = write_if_changed(os.path.join(project, ".vibecoding", "AGENTS.block.md"),
                                           desired_block.encode("utf-8"), journal)

            # 4) evidence/_template.md
            journal.step = ".vibecoding/evidence/_template.md"
            state_ev = write_if_changed(
                os.path.join(project, ".vibecoding", "evidence", "_template.md"),
                EVIDENCE_TEMPLATE.format(sv=SKILL_VERSION, task="<TASK-ID>", ts="<日期 时间 时区>",
                                         baseline="<commit>", env="<系统 / 运行时>").encode("utf-8"),
                journal)

            # 5) HANDOFF.md（仅在不存在时创建）
            journal.step = ".vibecoding/HANDOFF.md"
            handoff = os.path.join(project, ".vibecoding", "HANDOFF.md")
            if not os.path.exists(handoff):
                ws = "%s @ %s" % (state["branch"], state["head"][:12]) if state["is_repo"] else project
                baseline = state["head"] if state["is_repo"] else "无版本基线"
                journal.write(handoff, HANDOFF_TEMPLATE.format(
                    sv=SKILL_VERSION,
                    task="<TASK-ID>",
                    ts=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
                    workspace=ws,
                    baseline=baseline,
                    summary="（待填写）",
                    verify="（待填写）",
                    blocked="（待填写）",
                    effects="无",
                    hygiene="无",
                    next="（待填写）",
                ).encode("utf-8"), step=".vibecoding/HANDOFF.md 创建")
                state_ho = "created"

            # 6) 最后才动用户的 tracked 文件，缩短"已改用户文件"的时间窗
            journal.step = "AGENTS.md"
            plan["action"] = apply_agents(plan, desired_block, args.update_block, project, journal)
        except Exception as exc:  # 可控异常：回滚本次写入，不删除用户原有文件
            actions = journal.rollback()
            print("ERROR: 初始化失败，已按逆序回滚本次写入。")
            print("  失败步骤 : %s" % journal.step)
            print("  异常类型 : %s" % type(exc).__name__)
            print("  异常信息 : %s" % exc)
            print("--- 回滚动作 ---")
            for a in actions:
                print("  " + a)
            print("== 结论: FAILED（已回滚，退出码 1）==")
            return 1

        result["steps"].append(plan)
        result["steps"].append({"file": ".vibecoding/config.json", "status": state_cfg})
        result["steps"].append({"file": ".vibecoding/AGENTS.block.md", "status": state_block})
        result["steps"].append({"file": ".vibecoding/evidence/_template.md", "status": state_ev})
        result["steps"].append({"file": ".vibecoding/HANDOFF.md", "status": state_ho})

    claude_md = os.path.join(project, "CLAUDE.md")
    if os.path.exists(claude_md):
        result["manual_required"] = [
            "检测到 CLAUDE.md：本脚本不会编辑它。",
            "Claude Code 默认仅在工作目录及其上方都没有 CLAUDE.md 类文件时才读 AGENTS.md。",
            "解法一：Project instructions 设为 claude-md-and-agents-md。",
            "解法二：在 CLAUDE.md 首行加入 @AGENTS.md。",
        ]
    result["rc"] = 2 if plan["status"] == "differs" else 0

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("== Vibecoding 初始化（%s）==" % result["mode"])
        print("项目      : %s" % project)
        print("标准来源  : %s" % source)
        print("标准副本  : %s" % standard)
        print("标准校验  : rc=%s %s" % (result["standard"]["verify_rc"], "PASS" if result["standard"]["verify_rc"] == 0 else "见下"))
        for line in result["standard"]["verify_tail"]:
            print("            " + line)
        print("Git       : %s" % ("repo=%s branch=%s head=%s dirty=%s" % (state["is_repo"], state["branch"], (state["head"] or "")[:12], state["dirty"]) if state["is_repo"] else "非 Git 仓库"))
        print("--- 步骤 ---")
        for step in result["steps"]:
            print("  %-34s %-18s %s" % (step.get("file"), step.get("status"), step.get("action", "")))
        if result.get("manual_required"):
            print("--- 需人工处理 ---")
            for line in result["manual_required"]:
                print("  " + line)
        print("== 结论: %s ==" % ("NEED_DECISION（标记块 differs）" if result["rc"] == 2 else "OK"))
    return result["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
