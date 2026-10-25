# -*- coding: utf-8 -*-
"""Vibecoding规范 发布包构建与校验工具。

位置：tools/release_zip.py
根目录由脚本自身位置推断（上一级）。

用法：
    python tools/release_zip.py inspect <zip路径> [成员名]
        列出 ZIP 条目；给成员名（如 CHANGELOG.md）时打印其文本内容。
    python tools/release_zip.py build <输出zip路径>
        依据 MANIFEST.sha256 打包：包内文件 = 清单全部条目 + 清单自身，
        统一置于顶层目录 Vibecoding规范/ 之下。
        清单未列出的文件（含 _review_*/、_dist/、_archive/ 等）不会进入发布包。
    python tools/release_zip.py verify <zip路径>
        校验：顶层目录唯一为 Vibecoding规范/；条目集 == 清单 + 清单自身；
        每个条目 SHA-256 与磁盘清单一致；无评审/分发/历史目录或缓存混入。
    python tools/release_zip.py verify-self <zip路径>
        用 ZIP 内自带的 MANIFEST.sha256 校验该包自身（用于历史发布包）。

退出码：0=通过；1=校验不通过；2=用法错误。
"""
import hashlib
import os
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "MANIFEST.sha256")
TOP = "Vibecoding规范/"

# 绝不允许进入发布包的目录前缀与文件名特征
FORBIDDEN_DIRS = {".git", "_archive", "_dist", "__pycache__"}
FORBIDDEN_SUFFIXES = (".pyc", ".tmp")


def forbidden(rel):
    """Match whole path components; exclude every `_review_*` directory."""
    parts = rel.split("/")
    return any(p in FORBIDDEN_DIRS or p.startswith("_review_")
               or p == ".DS_Store" or p.endswith(FORBIDDEN_SUFFIXES)
               for p in parts)


def safe_relative(rel, *, allow_history=False):
    """Reject traversal, absolute/drive paths, noncanonical separators and symlink escapes."""
    if (not rel or "\\" in rel or "\x00" in rel or ":" in rel or
            rel.startswith("/") or rel.endswith("/") or
            any(part in ("", ".", "..") for part in rel.split("/")) or
            (forbidden(rel) and not allow_history) or rel == "MANIFEST.sha256"):
        return False
    path = os.path.realpath(os.path.join(ROOT, *rel.split("/")))
    return os.path.commonpath((os.path.realpath(ROOT), path)) == os.path.realpath(ROOT)


def parse_manifest(text, *, allow_history=False):
    entries = {}
    for row, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) \*(.+)", line)
        if not match:
            raise ValueError(f"MANIFEST 第 {row} 行格式错误")
        digest, name = match.groups()
        if not safe_relative(name, allow_history=allow_history):
            raise ValueError(f"MANIFEST 第 {row} 行包含无效路径: {name!r}")
        if name in entries:
            raise ValueError(f"MANIFEST 中有重复条目: {name}")
        entries[name] = digest.lower()
    if not entries:
        raise ValueError("MANIFEST 不允许为空")
    return entries



def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return parse_manifest(f.read())


def cmd_inspect(argv):
    if not argv:
        print(__doc__)
        return 2
    zp = argv[0]
    member = argv[1] if len(argv) > 1 else None
    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        print(f"ZIP: {zp}")
        print(f"条目数: {len(names)}")
        for n in names:
            print(f"  {zf.getinfo(n).file_size:>8}  {n}")
        if member:
            print(f"\n---- {member} ----")
            print(zf.read(member).decode("utf-8", errors="replace"))
    return 0


def cmd_build(argv):
    if not argv:
        print(__doc__)
        return 2
    out = os.path.abspath(argv[0])
    entries = load_manifest()
    files = sorted(entries) + ["MANIFEST.sha256"]
    missing = [n for n in files if not os.path.isfile(os.path.join(ROOT, n.replace("/", os.sep)))]
    if missing:
        print("!! 缺文件，拒绝打包：")
        for n in missing:
            print("  -", n)
        return 1
    mismatches = [n for n in entries if sha256_file(os.path.join(ROOT, *n.split("/"))) != entries[n]]
    if mismatches:
        print("!! 清单哈希与工作文件不一致，拒绝打包；请先核查并显式更新清单：")
        for n in mismatches:
            print("  -", n)
        return 1
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(os.path.join(ROOT, rel.replace("/", os.sep)), TOP + rel)
    print(f"已打包 {len(files)} 个文件 -> {out}")
    print(f"顶层目录: {TOP}")
    return 0


def cmd_verify(argv):
    if not argv:
        print(__doc__)
        return 2
    zp = argv[0]
    entries = load_manifest()
    expected = set(entries) | {"MANIFEST.sha256"}

    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        actual, bad_top = set(), []
        for n in names:
            if not n.startswith(TOP) or n == TOP:
                bad_top.append(n)
                continue
            actual.add(n[len(TOP):])
        duplicates = sorted({n for n in names if names.count(n) > 1})
        unsafe = sorted(r for r in actual if not safe_relative(r) and r != "MANIFEST.sha256")
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        dirty = sorted(r for r in actual if forbidden(r))
        bad_hash = []
        for rel in sorted(actual & expected):
            if rel == "MANIFEST.sha256":
                continue
            got = hashlib.sha256(zf.read(TOP + rel)).hexdigest()
            if got != entries.get(rel, ""):
                bad_hash.append((rel, entries.get(rel, "")[:16], got[:16]))
        manifest_same = zf.read(TOP + "MANIFEST.sha256") == open(MANIFEST, "rb").read()

    print(f"ZIP: {zp}")
    print(f"条目数: {len(names)}；期望条目数: {len(expected)}")
    if bad_top:
        print("!! 顶层目录不合规条目:"); [print("  -", n) for n in bad_top]
    if missing:
        print("!! 包内缺少（清单登记但 ZIP 没有）:"); [print("  -", n) for n in missing]
    if extra:
        print("!! 包内多出（清单未登记）:"); [print("  -", n) for n in extra]
    if dirty:
        print("!! 包内含禁止内容（历史目录/缓存）:"); [print("  -", n) for n in dirty]
    if duplicates:
        print("!! ZIP 存在重复条目:"); [print("  -", n) for n in duplicates]
    if unsafe:
        print("!! ZIP 存在非法成员路径:"); [print("  -", n) for n in unsafe]
    if bad_hash:
        print("!! 哈希与清单不一致:")
        for rel, e, a in bad_hash:
            print(f"  - {rel}  期望 {e}… 实际 {a}…")
    if not manifest_same:
        print("!! 包内 MANIFEST.sha256 与磁盘清单字节不一致")
    ok = not (bad_top or missing or extra or dirty or bad_hash or duplicates or unsafe) and manifest_same
    print(f"\n== ZIP 校验: {'PASS' if ok else 'FAIL'}"
          f"（顶层合规 {'是' if not bad_top else '否'} / 缺 {len(missing)} / 多 {len(extra)}"
          f" / 违禁 {len(dirty)} / 哈希不符 {len(bad_hash)} / 清单一致 {'是' if manifest_same else '否'}）==")
    return 0 if ok else 1


def cmd_verify_self(argv):
    """用 ZIP 内自带的 MANIFEST.sha256 校验该 ZIP 自身（用于历史发布包）。"""
    if not argv:
        print(__doc__)
        return 2
    zp = argv[0]
    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
        manifest_name = next((n for n in names if n.endswith("MANIFEST.sha256")), None)
        if not manifest_name:
            print("!! 包内没有 MANIFEST.sha256")
            return 1
        top = manifest_name[: -len("MANIFEST.sha256")]
        entries = parse_manifest(zf.read(manifest_name).decode("utf-8"), allow_history=True)
        actual = {n[len(top):] for n in names if n != manifest_name}
        missing = sorted(set(entries) - actual)
        extra = sorted(actual - set(entries))
        bad = []
        for rel in sorted(actual & set(entries)):
            got = hashlib.sha256(zf.read(top + rel)).hexdigest()
            if got != entries[rel]:
                bad.append((rel, entries[rel][:16], got[:16]))
    print(f"ZIP: {zp}")
    print(f"包内清单登记 {len(entries)} 项；实际条目 {len(actual)}")
    if missing: print("!! 缺:", *missing)
    if extra: print("!! 多:", *extra)
    if bad:
        print("!! 哈希不符:")
        for rel, e, a in bad:
            print(f"  - {rel}  期望 {e}… 实际 {a}…")
    ok = not (missing or extra or bad)
    print(f"== 自校验: {'PASS' if ok else 'FAIL'}（缺 {len(missing)} / 多 {len(extra)} / 哈希不符 {len(bad)}）==")
    return 0 if ok else 1


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("inspect", "build", "verify", "verify-self"):
        print(__doc__)
        return 2
    try:
        return {"inspect": cmd_inspect, "build": cmd_build,
                "verify": cmd_verify, "verify-self": cmd_verify_self}[sys.argv[1]](sys.argv[2:])
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        print(f"!! 发布或校验失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
