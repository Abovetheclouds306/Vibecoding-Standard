# -*- coding: utf-8 -*-
"""Vibecoding规范 — 文档引用检查（只读）。

位置：tools/check_links.py
根目录由脚本自身位置推断（上一级）。

检查发布范围内所有 Markdown 的相对链接与图片引用是否指向存在的文件，
并可检查关键路径（`agents/`、`templates/`、`tools/`）是否齐备。
文件名含空格的链接请使用 `%20` 或尖括号写法；本工具按原样做路径解析。

用法：
    python tools/check_links.py [--require <相对路径> ...]

退出码：0 = 通过；1 = 存在失效链接或缺失的必需路径。
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 本地追溯材料目录：不参与引用检查
EXCLUDE_DIRS = {"_dist", "_archive", "__pycache__"}


def skip_dir(d):
    return d in EXCLUDE_DIRS or d.startswith("_review_")
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SKIP_PREFIX = ("http://", "https://", "mailto:", "#")


def main(argv):
    require = []
    if "--require" in argv:
        i = argv.index("--require")
        require = argv[i + 1:]

    files, total, bad = 0, 0, []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not skip_dir(d)]
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            files += 1
            p = os.path.join(dirpath, fn)
            for m in LINK.finditer(open(p, encoding="utf-8").read()):
                target = m.group(1).strip()
                if target.startswith(SKIP_PREFIX):
                    continue
                target = target.split("#")[0].strip().strip("<>")
                if not target:
                    continue
                total += 1
                ap = os.path.normpath(os.path.join(dirpath, target.replace("/", os.sep)))
                if not os.path.exists(ap):
                    bad.append((os.path.relpath(p, ROOT), target))

    missing_req = [r for r in require
                   if not os.path.exists(os.path.join(ROOT, r.replace("/", os.sep)))]

    print(f"根目录        : {ROOT}")
    print(f"扫描 Markdown : {files} 个")
    print(f"相对链接      : {total} 条")
    print(f"失效链接      : {len(bad)}")
    for r, t in bad:
        print(f"  !! {r} -> {t}")
    if require:
        print(f"必需路径      : 检查 {len(require)} 项，缺失 {len(missing_req)}")
        for r in missing_req:
            print(f"  !! 缺失 {r}")

    ok = not bad and not missing_req
    print(f"== 引用检查: {'PASS' if ok else 'FAIL'} ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
