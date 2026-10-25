#!/usr/bin/env python3
"""vb_handoff.py — 会话交接与恢复。

写：把基线、工作区、验证结论、阻塞与下一步写进 .vibecoding/HANDOFF.md（脚本托管，带生成标记）。
读：--show 输出恢复所需的五段信息（交接正文 / 当前基线 / 证据清单 / 配置 / 建议下一步）。

退出码：0 = 正常；1 = 拒绝（HANDOFF.md 非本工具生成且未 --force）或出错。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

SKILL_VERSION = "0.1.0"
MARK = "<!-- generated-by: vb_handoff"


def run(args: list[str], cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, shell=False)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", "command not found: %s" % args[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def git(project: str, *args: str) -> tuple[int, str]:
    rc, out, err = run(["git", *args], cwd=project)
    return rc, (out if rc == 0 else err).strip()


def now() -> str:
    dt = datetime.now().astimezone()
    s = dt.strftime("%Y-%m-%d %H:%M:%S %z")
    if len(s) >= 6 and s[-5] in "+-":
        s = s[:-5] + s[-5:-2] + ":" + s[-2:]
    return s


def baseline(project: str) -> tuple[str, str]:
    rc, head = git(project, "rev-parse", "HEAD")
    if rc != 0:
        return "无版本基线（非 Git 仓库）", "（无）"
    _, branch = git(project, "rev-parse", "--abbrev-ref", "HEAD")
    _, status = git(project, "status", "--porcelain")
    base = "commit %s (branch %s, %s)" % (head[:12], branch, "dirty" if status else "clean")
    return base, (status or "（工作区干净）")


def conclusion_of(path: str) -> str:
    try:
        text = open(path, "rb").read().decode("utf-8", "replace")
    except OSError:
        return "（不可读）"
    m = re.search(r"^结论：\s*(.+)$", text, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"== 证据门禁:\s*(\w+)\s*==", text)
    return m.group(1) if m else "（未找到结论行）"


def build_body(args, project: str) -> str:
    base, status = baseline(project)
    rc, top = git(project, "rev-parse", "--show-toplevel")
    ws = os.path.relpath(top, project).replace("\\", "/") if rc == 0 else project
    return (
        MARK + " v%s -->\n" % SKILL_VERSION
        + "# %s 交接\n\n" % args.task
        + "Updated: %s\n" % now()
        + "Task source: 见项目自身任务系统（本文件不复制任务状态）\n"
        + "Workspace: %s（分支/提交见 Baseline）\n" % (ws or ".")
        + "Baseline: %s\n\n" % base
        + "## 已完成\n%s\n\n" % args.done
        + "## 验证\n%s\n\n" % args.verify
        + "## 未完成与阻塞\n%s\n\n" % args.blocked
        + "## 已发生的外部效果\n%s\n\n" % args.effects
        + "## 工作区卫生\n%s\n\n" % args.hygiene
        + "## 恢复步骤\n"
        + "1. `git status --porcelain` 核对未提交改动的归属（当前状态见下方 recover 输出）。\n"
        + "2. 读 `.vibecoding/evidence/` 下相关证据，核对结论与退出码。\n"
        + "3. 按「未完成与阻塞」继续，不重跑已有副作用的步骤。\n\n"
        + "## 下一步\n%s\n" % args.next
    )


def show(project: str) -> int:
    ho = os.path.join(project, ".vibecoding", "HANDOFF.md")
    cfg = os.path.join(project, ".vibecoding", "config.json")
    ev_dir = os.path.join(project, ".vibecoding", "evidence")

    print("== 恢复信息（%s）==" % project)
    print("\n--- 1. 交接正文 ---")
    if os.path.exists(ho):
        print(open(ho, "rb").read().decode("utf-8", "replace").strip())
    else:
        print("（无 HANDOFF.md：这不是一个已完成初始化的项目，或尚未建立交接）")

    base, status = baseline(project)
    print("\n--- 2. 当前基线 ---")
    print("基线: %s" % base)
    print("未提交改动:")
    print(status)

    print("\n--- 3. 证据清单 ---")
    files = sorted(glob.glob(os.path.join(ev_dir, "*.md")))
    files = [f for f in files if os.path.basename(f) != "_template.md"]
    if not files:
        print("（无证据文件）")
    for f in files:
        print("  %-40s 结论=%s" % (os.path.basename(f), conclusion_of(f)))

    print("\n--- 4. 配置 ---")
    if os.path.exists(cfg):
        try:
            data = json.loads(open(cfg, "rb").read().decode("utf-8"))
            for k in ("skill_version", "standard_version", "standard_signoff_commit", "standard_release_commit", "initialized_at"):
                print("  %-28s %s" % (k, data.get(k)))
        except json.JSONDecodeError:
            print("  （config.json 解析失败）")
    else:
        print("（无 config.json）")

    print("\n--- 5. 建议下一步 ---")
    if os.path.exists(ho):
        text = open(ho, "rb").read().decode("utf-8", "replace")
        m = re.search(r"## 下一步\n(.+?)(\n## |\Z)", text, re.S)
        print((m.group(1).strip() if m else "（交接里没有「下一步」）"))
    unresolved = [f for f in files if conclusion_of(f) not in ("PASS",)]
    if unresolved:
        print("未闭环证据（结论非 PASS）：")
        for f in unresolved:
            print("  - %s（结论=%s）" % (os.path.basename(f), conclusion_of(f)))
    else:
        print("未闭环证据：无")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Vibecoding 会话交接与恢复")
    ap.add_argument("--project", default=".")
    ap.add_argument("--task", help="任务 ID（写模式必填）")
    ap.add_argument("--done", default="（待填写）")
    ap.add_argument("--verify", default="（待填写）")
    ap.add_argument("--blocked", default="无")
    ap.add_argument("--effects", default="无")
    ap.add_argument("--hygiene", default="无")
    ap.add_argument("--next", dest="next", default="（待填写）")
    ap.add_argument("--show", action="store_true", help="读模式：输出恢复所需信息")
    ap.add_argument("--force", action="store_true", help="允许覆盖非本工具生成的 HANDOFF.md")
    args = ap.parse_args(argv)

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print("ERROR: 项目目录不存在: %s" % project)
        return 1

    if args.show:
        return show(project)

    if not args.task:
        print("ERROR: 写模式需要 --task；只读恢复请用 --show")
        return 1

    ho = os.path.join(project, ".vibecoding", "HANDOFF.md")
    if os.path.exists(ho) and not args.force:
        head = open(ho, "rb").read(4096).decode("utf-8", "replace")
        if MARK not in head:
            print("REFUSED: HANDOFF.md 非本工具生成（可能由用户手写），拒绝覆盖：%s" % ho)
            print("         确认要覆盖请加 --force。")
            return 1
    os.makedirs(os.path.dirname(ho), exist_ok=True)
    open(ho, "wb").write(build_body(args, project).encode("utf-8"))
    print("== 交接已写入 ==")
    print("  %s" % ho)
    print("  任务: %s" % args.task)
    print("  基线: %s" % baseline(project)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
