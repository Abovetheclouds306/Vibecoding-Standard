# -*- coding: utf-8 -*-
"""Vibecoding规范 — MANIFEST.sha256 完整性校验（只读，不修改任何原始文件）。

位置：tools/verify_manifest.py
根目录由脚本自身位置推断（上一级），解压到任意路径均可运行。

输出：登记文件数 / 逐项结果 / 失败项 / 缺失项 / 未登记文件 / 汇总结论。
退出码：0 = 通过；1 = 不通过。
"""
import hashlib
import os
import sys

from release_zip import load_manifest

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "MANIFEST.sha256")
# 本地追溯材料与缓存目录：不进发布包，也不计入"未登记文件"
SELF_DIRS = {".git", "_dist", "_archive", "__pycache__"}
# 仓库自身 CI 配置目录（相对根目录，精确匹配）：属仓库集成设施，不进入分发给用户的
# 规范发布包，因此不计入"未登记文件"。此处只排除这一条明确路径；`.github/` 下的其他
# 内容（如 ISSUE_TEMPLATE、CODEOWNERS）仍按未登记文件校验，不会被一并放过。
SELF_PATHS = {".github/workflows"}


def skip_dir(name):
    """按目录名排除本地材料与缓存（对任意层级生效）。"""
    return name in SELF_DIRS or name.startswith("_review_")


def skip_path(rel):
    """按相对根目录的完整路径排除仓库自身 CI 配置（仅精确匹配，不按目录名匹配）。"""
    return rel in SELF_PATHS


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.isfile(MANIFEST):
        print(f"!! 未找到清单：{MANIFEST}")
        return 1

    try:
        entries = load_manifest()
    except (ValueError, OSError) as exc:
        print(f"!! 清单无效: {exc}")
        return 1
    print(f"根目录        : {ROOT}")
    print(f"MANIFEST 登记 : {len(entries)} 项")

    ok, bad, missing = [], [], []
    for name, expect in sorted(entries.items()):
        path = os.path.join(ROOT, name.replace("/", os.sep))
        if not os.path.isfile(path):
            missing.append(name)
            continue
        actual = sha256(path)
        (ok if actual == expect else bad).append((name, expect, actual))

    print(f"通过          : {len(ok)}")
    if bad:
        print(f"\n!! 校验失败 {len(bad)} 项:")
        for name, e, a in bad:
            print(f"  {name}\n    期望 {e[:16]}… 实际 {a[:16]}…")
    if missing:
        print(f"\n!! 清单登记但文件缺失 {len(missing)} 项:")
        for name in missing:
            print(f"  {name}")

    registered = set(entries)
    unregistered = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        kept = []
        for name in dirnames:
            child = name if rel_dir == "." else f"{rel_dir}/{name}"
            if skip_dir(name) or skip_path(child):
                continue
            kept.append(name)
        dirnames[:] = kept
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            # 普通 clone 是 `.git/` 目录，worktree 则是根目录 `.git` 指针文件；两者都不属于发布内容。
            if rel in {"MANIFEST.sha256", ".git"}:
                continue
            if rel not in registered:
                unregistered.append(rel)
    print(f"未登记文件    : {len(unregistered)}")
    for rel in sorted(unregistered):
        print(f"  {rel}")

    verdict = "PASS" if not bad and not missing and not unregistered else "FAIL"
    print(f"\n== 清单校验: {verdict}"
          f"（通过 {len(ok)} / 失败 {len(bad)} / 缺失 {len(missing)} / 未登记 {len(unregistered)}）==")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
