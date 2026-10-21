# -*- coding: utf-8 -*-
"""Vibecoding规范 — 更新 MANIFEST.sha256（带防呆）。

位置：tools/update_manifest.py
根目录由脚本自身位置推断（上一级）。

流程要求：先跑 `verify_manifest.py` 看清差异，再把差异显式写进本命令；
本脚本拒绝"不确认异常就重算清单"的用法。

用法：
    python tools/update_manifest.py --expect <允许哈希变化的相对路径>... [--add <新增文件相对路径>...]

规则（任一不满足即整体拒绝、不写盘）：
- 未给出任何 --expect/--add 时拒绝执行；
- 清单登记的文件缺失 → 拒绝；
- 出现未声明的哈希变化 → 拒绝并列出；
- 已声明但实际未变化的文件 → 拒绝（期望与事实不符）；
- --expect 出现不在清单中的文件、--add 文件不存在或已在清单中 → 拒绝；
- 重排后若会改变既有条目顺序 → 拒绝（防止静默重排）。

写入时按名称排序输出，保持 "<hash> *<name>" 格式。
"""
import hashlib
import os
import sys

from release_zip import load_manifest, safe_relative

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "MANIFEST.sha256")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    expect, add = [], []
    mode = None
    for a in argv:
        if a == "--expect":
            mode = expect
        elif a == "--add":
            mode = add
        elif a.startswith("--"):
            print(f"未知参数: {a}")
            print(__doc__)
            return 2
        elif mode is not None:
            mode.append(a.replace("\\", "/"))
        else:
            print(f"未知参数: {a}")
            print(__doc__)
            return 2
    if not expect and not add:
        print("!! 必须显式声明 --expect（允许变化的文件）和/或 --add（新增文件）。")
        print("!! 先运行 verify_manifest.py 查看差异，把已确认的差异写进命令；拒绝盲目重算。")
        return 2

    invalid = [n for n in expect + add if not safe_relative(n)]
    if invalid or len(set(expect)) != len(expect) or len(set(add)) != len(add):
        print("!! 路径非法或声明重复，拒绝修改清单:", invalid)
        return 1
    try:
        validated = load_manifest()
    except (ValueError, OSError) as exc:
        print(f"!! 现有清单非法，拒绝修改: {exc}")
        return 1

    order, old = [], {}
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            digest, name = line.split(" *", 1)
            name = name.strip()
            order.append(name)
            old[name] = digest.strip().lower()

    if old != validated:
        print("!! 清单条目校验不一致，拒绝修改")
        return 1
    errors = []

    missing = [n for n in order if not os.path.isfile(os.path.join(ROOT, n.replace("/", os.sep)))]
    if missing:
        errors.append(("清单登记但文件缺失", missing))

    new_hashes, changed = {}, []
    for n in order:
        p = os.path.join(ROOT, n.replace("/", os.sep))
        if not os.path.isfile(p):
            continue
        h = sha256(p)
        new_hashes[n] = h
        if h != old[n]:
            changed.append(n)
    undeclared = [n for n in changed if n not in expect]
    if undeclared:
        errors.append(("未声明但已变化", undeclared))
    not_changed = [n for n in expect if n not in changed]
    if not_changed:
        errors.append(("已声明但实际未变化", not_changed))
    unknown_expect = [n for n in expect if n not in old]
    if unknown_expect:
        errors.append(("--expect 中有不在清单里的文件", unknown_expect))

    for n in add:
        p = os.path.join(ROOT, n.replace("/", os.sep))
        if not os.path.isfile(p):
            errors.append(("--add 文件不存在", [n]))
        elif n in old:
            errors.append(("--add 文件已在清单中（重复登记）", [n]))

    if errors:
        print("!! 拒绝写盘，问题如下：")
        for label, items in errors:
            print(f"- {label}:")
            for n in items:
                print(f"    {n}")
        print("（MANIFEST.sha256 未被修改。先处理差异或修正声明后重试。）")
        return 1

    final_names = sorted(set(order) | set(add))
    if [n for n in final_names if n in old] != order:
        print("!! 排序重排会改变既有条目顺序，拒绝写盘（请检查清单格式与命名）。")
        return 1

    lines_out, changed_out, added_out = [], [], []
    for n in final_names:
        h = new_hashes.get(n) or sha256(os.path.join(ROOT, n.replace("/", os.sep)))
        if n in add:
            added_out.append(n)
        elif h != old[n]:
            changed_out.append(n)
        lines_out.append(f"{h} *{n}\n")

    with open(MANIFEST, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines_out)

    print(f"MANIFEST 已更新：变更 {len(changed_out)} / 新增 {len(added_out)} / 合计 {len(final_names)} 项")
    for n in changed_out:
        print("  ~", n)
    for n in added_out:
        print("  +", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
