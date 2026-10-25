#!/usr/bin/env python3
"""install_skill.py — 把 vibecoding 技能安装到目标 Agent 的技能目录（只复制 + 校验）。

不做的事：不改宿主的 settings/config，不写 CLAUDE.md/AGENTS.md，不联网，不删任何文件。

退出码：0 = 成功/无变化；1 = 拒绝或校验失败；2 = 需要人工决定（目标已存在且内容不同）。
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys

TARGETS = {
    "claude-code": {"project": ".claude/skills", "user": ".claude/skills"},
    "codex": {"project": ".agents/skills", "user": ".agents/skills"},
    "cursor": {"project": ".cursor/skills", "user": ".cursor/skills"},
    "workbuddy": {"project": ".codebuddy/skills", "user": ".codebuddy/skills"},
    "workbuddy-alt": {"project": ".workbuddy/skills", "user": ".workbuddy/skills"},
}

# 不随技能分发的产物：字节码缓存、编辑器/系统垃圾、打包中间件。
# 判据：这些文件与技能语义无关，且 pyc 会随宿主 Python 版本变化 ⇒ 会让"幂等"误判为"内容不同"。
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db", "*.egg-info")


def _ignored(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if "__pycache__" in parts:
        return True
    return parts[-1].endswith((".pyc", ".pyo")) or parts[-1] in (".DS_Store", "Thumbs.db")


def run(args, cwd=None, timeout=300):
    p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, shell=False)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def diff_dirs(a: str, b: str) -> tuple[list[str], list[str]]:
    """返回 (仅源有, 内容不同) 列表。忽略 IGNORE 命中的构建产物。"""
    only_src, differ = [], []
    for root, _, files in os.walk(a):
        for f in files:
            src = os.path.join(root, f)
            rel = os.path.relpath(src, a)
            if _ignored(rel):
                continue
            dst = os.path.join(b, rel)
            if not os.path.exists(dst):
                only_src.append(rel)
            elif not filecmp.cmp(src, dst, shallow=False):
                differ.append(rel)
    return only_src, differ


def main(argv):
    ap = argparse.ArgumentParser(description="安装 vibecoding 技能")
    ap.add_argument("--target", required=True, choices=sorted(TARGETS), help="目标平台目录约定")
    ap.add_argument("--scope", default="project", choices=["project", "user"])
    ap.add_argument("--project", default=".", help="scope=project 时的项目根")
    ap.add_argument("--path", help="显式指定技能根目录（覆盖平台默认约定）")
    ap.add_argument("--source", help="技能源目录（默认本脚本的上两级）")
    ap.add_argument("--force", action="store_true", help="目标已存在且内容不同时允许覆盖")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    source = os.path.abspath(args.source or os.path.join(here, "..", "vibecoding"))
    if not os.path.isfile(os.path.join(source, "SKILL.md")):
        print("ERROR: 源目录不含 SKILL.md: %s" % source)
        return 1

    if args.path:
        root = args.path
    else:
        root = TARGETS[args.target][args.scope]
    if args.scope == "user":
        base = os.path.join(os.path.expanduser("~"), root)
    else:
        base = os.path.join(os.path.abspath(args.project), root)
    dest = os.path.join(base, "vibecoding")

    print("== 安装 vibecoding 技能 ==")
    print("源      : %s" % source)
    print("目标    : %s" % dest)
    print("模式    : %s" % ("dry-run" if args.dry_run else "apply"))

    rc = 0
    if os.path.exists(dest):
        only_src, differ = diff_dirs(source, dest)
        print("已存在  : 是（仅源有 %d 个文件，内容不同 %d 个）" % (len(only_src), len(differ)))
        if only_src or differ:
            print("  仅源有:", only_src[:5])
            print("  内容不同:", differ[:5])
            if not args.force:
                print("REFUSED: 目标存在且与源不同；确认覆盖请加 --force。")
                return 2
            if not args.dry_run:
                shutil.rmtree(dest)
                shutil.copytree(source, dest, ignore=IGNORE)
                print("  已覆盖（--force）")
        else:
            print("  内容一致，无需复制（幂等）")
    else:
        if not args.dry_run:
            os.makedirs(base, exist_ok=True)
            shutil.copytree(source, dest, ignore=IGNORE)
            print("  已复制")

    if args.dry_run:
        print("== dry-run 结束，未写盘 ==")
        return 0

    # 安装后校验：入口存在 + 标准副本完整
    ok_skill = os.path.isfile(os.path.join(dest, "SKILL.md"))
    vm = os.path.join(dest, "vendor", "vibecoding-standard", "tools", "verify_manifest.py")
    ok_std = None
    if os.path.isfile(vm):
        vrc, out, err = run([sys.executable, vm], cwd=os.path.dirname(os.path.dirname(vm)))
        ok_std = (vrc == 0)
        print("标准校验: rc=%d %s" % (vrc, [l for l in (out + err).strip().splitlines() if l.strip()][-1:]))
    print("入口校验: SKILL.md %s" % ("OK" if ok_skill else "MISSING"))
    if not ok_skill or ok_std is False:
        rc = 1
    print("== %s ==" % ("安装完成" if rc == 0 else "安装完成但有校验失败"))
    print("提示：WorkBuddy 类宿主在会话启动时注入技能列表，需**新开会话**才会发现新技能；Codex 会自动检测，未生效则重启。")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
