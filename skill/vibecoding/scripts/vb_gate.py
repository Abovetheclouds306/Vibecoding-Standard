#!/usr/bin/env python3
"""vb_gate.py — 验证证据门禁：跑命令 → 写证据 → 调标准 check_evidence.py → 汇总退出码。

语义（与 Vibecoding v1.2.7 一致，严重度 1 > 2 > 0）：
  0 = PASS    全部验证已运行且退出码 0，证据结构校验通过
  1 = FAIL    任一验证退出码非 0，或证据中可靠解析出失败
  2 = UNKNOWN 有验证未运行 / 证据结构不足 / 需要人工决定

铁律：未运行 != 通过。没有 --verify 时结论必为 NOT_RUN（退出码 2），不得输出 PASS。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

SKILL_VERSION = "0.1.0"
GENERATED_MARK = "<!-- generated-by: vb_gate"
SEVERITY_NAME = {0: "PASS", 1: "FAIL", 2: "UNKNOWN"}


def now_with_offset() -> str:
    dt = datetime.now().astimezone()
    base = dt.strftime("%Y-%m-%d %H:%M:%S %z")
    if len(base) >= 6 and (base[-5] in "+-"):
        base = base[:-5] + base[-5:-2] + ":" + base[-2:]
    return base


def run(args: list[str], cwd: str | None = None, timeout: int = 300) -> tuple[int, str, str]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, shell=False)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", "command not found: %s" % args[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout


def run_shell(cmd: str, cwd: str, timeout: int) -> tuple[int, str, str]:
    """用户命令按其宿主 shell 语义执行；超时记 124，命令不存在记 127。"""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout, shell=True)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout


def git(project: str, *args: str) -> tuple[int, str]:
    rc, out, err = run(["git", *args], cwd=project)
    return rc, (out if rc == 0 else err).strip()


def git_brief(project: str) -> str:
    rc, head = git(project, "rev-parse", "HEAD")
    if rc != 0:
        return "无版本基线（非 Git 仓库）"
    _, branch = git(project, "rev-parse", "--abbrev-ref", "HEAD")
    _, status = git(project, "status", "--porcelain")
    dirty = "dirty" if status else "clean"
    return "commit %s (branch %s, %s)" % (head[:12], branch, dirty)


def find_standard(explicit: str | None, project: str) -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    if explicit:
        cands.append(explicit)
    env = os.environ.get("VB_STANDARD_HOME")
    if env:
        cands.append(env)
    cands.append(os.path.normpath(os.path.join(here, "..", "vendor", "vibecoding-standard")))
    cands.append(os.path.join(project, ".vibecoding", "vendor", "vibecoding-standard"))
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "tools", "check_evidence.py")):
            return os.path.abspath(c)
    return None


def worst(codes: list[int]) -> int:
    if any(c == 1 for c in codes):
        return 1
    if any(c == 2 for c in codes):
        return 2
    if all(c == 0 for c in codes) and codes:
        return 0
    return 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Vibecoding 验证证据门禁")
    ap.add_argument("--project", default=".", help="项目目录")
    ap.add_argument("--task", required=True, help="任务 ID（用于证据文件名与 Task 字段）")
    ap.add_argument("--verify", action="append", default=[], help="验证命令，可重复；同一命令只跑一次")
    ap.add_argument("--evidence", help="证据文件路径（默认 .vibecoding/evidence/<TASK>.md）")
    ap.add_argument("--task-status", default="REVIEW", choices=["DONE", "REVIEW", "IN_PROGRESS", "BLOCKED"], help="任务状态；DONE 才做完整性检查")
    ap.add_argument("--standard", help="标准副本目录")
    ap.add_argument("--check-standard", action="store_true", help="额外校验标准副本完整性（作为 AC-000，不参与 PASS 判定时仍记录）")
    ap.add_argument("--timeout", type=int, default=900, help="单条命令超时秒数")
    ap.add_argument("--force", action="store_true", help="允许覆盖非本工具生成的证据文件")
    ap.add_argument("--no-write", action="store_true", help="只跑命令、不写证据文件")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args(argv)

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print("ERROR: 项目目录不存在: %s" % project)
        return 1

    # 同一命令重复传入只执行一次（幂等，避免重复副作用）
    seen: list[str] = []
    for cmd in args.verify:
        if cmd not in seen:
            seen.append(cmd)

    evidence_path = args.evidence or os.path.join(project, ".vibecoding", "evidence", "%s.md" % args.task)
    logs_dir = os.path.join(os.path.dirname(evidence_path), "logs")

    if os.path.exists(evidence_path) and not args.no_write:
        head = open(evidence_path, "rb").read(2048).decode("utf-8", "replace")
        if GENERATED_MARK not in head and not args.force:
            print("REFUSED: 证据文件非本工具生成，拒绝覆盖：%s" % evidence_path)
            print("         确认要覆盖请加 --force，或改用 --evidence 指定新路径。")
            return 1

    print("== Vibecoding 门禁 ==")
    print("项目      : %s" % project)
    print("任务      : %s" % args.task)
    print("基线      : %s" % git_brief(project))
    print("证据文件  : %s" % evidence_path)
    print("任务状态  : %s%s" % (args.task_status, "" if args.task_status == "DONE" else "（未执行 DONE 完整性检查）"))

    rows: list[dict] = []
    codes: list[int] = []
    ac = 0

    standard = find_standard(args.standard, project)
    if args.check_standard:
        ac += 1
        if not standard:
            rows.append({"id": "AC-%03d" % ac, "cmd": "verify_manifest.py", "rc": 2, "conclusion": "NOT_RUN", "log": "N/A", "limit": "未找到标准副本"})
            codes.append(2)
        else:
            rc, out, err = run([args.python, os.path.join(standard, "tools", "verify_manifest.py")], cwd=standard, timeout=300)
            tail = [l for l in (out + err).strip().splitlines() if l.strip()][-1:]
            os.makedirs(logs_dir, exist_ok=True)
            log_name = "%s-AC%03d.log" % (args.task, ac)
            open(os.path.join(logs_dir, log_name), "wb").write(
                ("$ python tools/verify_manifest.py (cwd=%s)\n\n[exit code] %d\n\n--- output ---\n%s\n" % (standard, rc, out + err)).encode("utf-8"))
            rows.append({"id": "AC-%03d" % ac, "cmd": "python tools/verify_manifest.py", "rc": rc,
                         "conclusion": "PASS" if rc == 0 else ("FAIL" if rc == 1 else "NOT_RUN"),
                         "log": "logs/" + log_name, "limit": (tail[0] if tail else "")[:80]})
            codes.append(rc)

    if not seen:
        print("--- 验证 ---")
        print("  （未提供 --verify：结论必为 NOT_RUN，不得判 PASS）")
        rows.append({"id": "AC-%03d" % (ac + 1 if ac else 1), "cmd": "（未提供验证命令）", "rc": None,
                     "conclusion": "NOT_RUN", "log": "N/A", "limit": "未运行任何验证"})
        codes.append(2)
        ac = ac + 1 if ac else 1
    else:
        os.makedirs(logs_dir, exist_ok=True)
        for cmd in seen:
            ac += 1
            start = datetime.now()
            rc, out, err = run_shell(cmd, project, args.timeout)
            dur = (datetime.now() - start).total_seconds()
            log_name = "%s-AC%03d.log" % (args.task, ac)
            log_path = os.path.join(logs_dir, log_name)
            body = "$ %s\n\n[exit code] %d\n[duration] %.1fs\n\n--- stdout ---\n%s\n--- stderr ---\n%s\n" % (cmd, rc, dur, out, err)
            try:
                open(log_path, "wb").write(body.encode("utf-8"))
                rel_log = "logs/" + log_name
            except OSError:
                rel_log = "N/A"
            # rc 0 -> PASS；rc 2 -> NOT_RUN(=UNKNOWN)；其余非零（1/124/127…）-> FAIL
            if rc == 0:
                conclusion = "PASS"
                limit = "仅本机环境"
            elif rc == 2:
                conclusion = "NOT_RUN"
                limit = "命令自报未完成（rc=2）：证据不足，不可作为通过依据"
            else:
                conclusion = "FAIL"
                limit = "仅本机环境"
            rows.append({"id": "AC-%03d" % ac, "cmd": cmd, "rc": rc, "conclusion": conclusion,
                         "log": rel_log, "limit": limit})
            codes.append(0 if rc == 0 else (2 if rc == 2 else 1))
            print("  [AC-%03d] rc=%-3d %.1fs  %s" % (ac, rc, dur, cmd))

    gate_rc = worst(codes)
    conclusion = SEVERITY_NAME[gate_rc]

    if not args.no_write:
        os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
        lines = [
            GENERATED_MARK + " v%s -->" % SKILL_VERSION,
            "# %s 验证记录" % args.task,
            "",
            "Task: %s" % args.task,
            "Time: %s" % now_with_offset(),
            "Baseline: %s" % git_brief(project),
            "Environment: %s / Python %s / cwd=%s" % (os.name, sys.version.split()[0], project),
            "",
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in rows:
            cmd = r["cmd"].replace("|", "\\|")
            rc_txt = "N/A" if r["rc"] is None else str(r["rc"])
            lines.append("| %s | `%s` | %s | %s | %s | %s |" % (r["id"], cmd, rc_txt, r["conclusion"], r["log"], r["limit"]))
        lines += [
            "",
            # 标准只允许 PASS / FAIL / BLOCKED / NOT_RUN；UNKNOWN 统一落成 NOT_RUN（未完成）
            "结论：%s" % {"PASS": "PASS", "FAIL": "FAIL", "UNKNOWN": "NOT_RUN"}[conclusion],
            "反向遗漏审查：待人工填写（本任务范围、确认的遗漏与处置）",
            "审查：待人工填写（审查者、版本、结论）；本文件由 vb_gate v%s 生成" % SKILL_VERSION,
            "Artifacts: %s" % ("logs/*.log" if seen else "N/A"),
            "Recheck Conditions: 代码、依赖或测试变更后须重跑本门禁",
            "Cleanup / Recovery: 日志保留于 evidence/logs/；无临时文件",
            "Release Status: 未涉及",
            "",
        ]
        open(evidence_path, "wb").write("\n".join(lines).encode("utf-8"))
        print("--- 证据已写入 ---")
        print("  %s" % evidence_path)

    # 用标准自带的证据门禁做结构校验（复用 v1.2.7 工具，不重写规则）
    struct_rc = 2
    if standard and not args.no_write:
        cmd = [args.python, os.path.join(standard, "tools", "check_evidence.py"), evidence_path,
               "--task-id", args.task, "--task-status", args.task_status]
        for r in rows:
            cmd += ["--acceptance-id", r["id"]]
        struct_rc, out, err = run(cmd, cwd=standard, timeout=300)
        print("--- 标准证据门禁（check_evidence.py）---")
        for line in (out + err).strip().splitlines():
            print("  " + line)
    elif not standard:
        print("--- 标准证据门禁 ---")
        print("  跳过：未找到标准副本，无法调用 check_evidence.py（结论不高于 UNKNOWN）")

    final_rc = worst([gate_rc, struct_rc])
    final_name = SEVERITY_NAME[final_rc]
    print("== Vibecoding 门禁: %s ==（命令汇总=%s / 结构校验=%s）" % (final_name, conclusion, SEVERITY_NAME.get(struct_rc, "UNKNOWN")))
    if final_rc != 0:
        print("   注意：%s 表示未通过或未验证；不得表述为通过。" % final_name)
    return final_rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
