#!/usr/bin/env python3
"""install_skill.py — 把 vibecoding 技能安装到目标 Agent 的技能目录（只复制 + 校验）。

不做的事：不改宿主的 settings/config，不写 CLAUDE.md/AGENTS.md，不联网，**不删任何文件**。

归属判定（INS-1）：
- 安装时在目标目录写 `.vibecoding-install.json`（安装清单：相对路径 -> sha256）。
- 只有「清单登记过、且当前内容仍等于登记哈希」的文件，才算本技能管理的文件，`--force` 才允许更新它。
- 内容与源完全相同的文件视为已同步（无需写入）。
- 其余一切（用户新增文件、被改过的已登记文件、无清单时内容不同的文件、目录/链接冲突）都不碰；
  若源需要写这些路径，则判为「归属不明冲突」，整体拒绝（退出码 2），一个文件也不写。
- `--force` 不再意味着删除目录：旧版的整目录 rmtree 已移除。
- 目标目录本身、其内任一路径分量为符号链接 / Junction / 其他重解析点时拒绝（退出码 1），不跟随。

退出码：0 = 成功/无变化；1 = 拒绝（边界/链接/源异常）、写入失败或校验失败；
2 = 需要人工决定（目标与源不同但未加 --force，或存在归属不明的冲突）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys

TARGETS = {
    "claude-code": {"project": ".claude/skills", "user": ".claude/skills"},
    "codex": {"project": ".agents/skills", "user": ".agents/skills"},
    "cursor": {"project": ".cursor/skills", "user": ".cursor/skills"},
    "workbuddy": {"project": ".codebuddy/skills", "user": ".codebuddy/skills"},
    "workbuddy-alt": {"project": ".workbuddy/skills", "user": ".workbuddy/skills"},
}

MANIFEST_NAME = ".vibecoding-install.json"
MANIFEST_KIND = "vibecoding-skill-install"

# 不随技能分发的产物：字节码缓存、编辑器/系统垃圾、打包中间件。
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db", "*.egg-info")


class BoundaryError(Exception):
    pass


def _ignored(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if "__pycache__" in parts or any(p.endswith(".egg-info") for p in parts):
        return True
    return parts[-1].endswith((".pyc", ".pyo")) or parts[-1] in (".DS_Store", "Thumbs.db")


def run(args, cwd=None, timeout=300):
    p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, shell=False)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def is_link_like(path: str) -> bool:
    """符号链接、Junction 或任何 Windows 重解析点。不存在返回 False。"""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if getattr(os.path, "isjunction", None) and os.path.isjunction(path):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def source_files(source: str) -> dict:
    """源技能文件清单 rel(posix) -> sha256。源内出现链接直接拒绝。"""
    out = {}
    for root, dirs, files in os.walk(source):
        for d in list(dirs):
            if is_link_like(os.path.join(root, d)):
                raise BoundaryError("源目录含链接，拒绝安装: %s" % os.path.join(root, d))
        dirs[:] = [d for d in dirs if not _ignored(os.path.relpath(os.path.join(root, d), source))]
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, source).replace(os.sep, "/")
            if _ignored(rel):
                continue
            if is_link_like(p):
                raise BoundaryError("源目录含链接，拒绝安装: %s" % p)
            if rel == MANIFEST_NAME:
                raise BoundaryError("源目录不应包含安装清单 %s" % MANIFEST_NAME)
            out[rel] = sha256_file(p)
    return out


def guard(dest: str, rel: str) -> str:
    """返回 dest 内 rel 的绝对路径；任何越界或经过链接的分量都抛 BoundaryError。"""
    parts = rel.split("/")
    if any(p in ("", ".", "..") for p in parts) or os.path.isabs(rel):
        raise BoundaryError("非法相对路径: %s" % rel)
    if is_link_like(dest):
        raise BoundaryError("目标目录本身是链接/重解析点: %s" % dest)
    cur = dest
    for p in parts:
        cur = os.path.join(cur, p)
        if is_link_like(cur):
            raise BoundaryError("路径分量是链接/重解析点，拒绝跟随: %s" % cur)
    real_dest = os.path.realpath(dest)
    real = os.path.realpath(cur)
    if os.path.commonpath([real_dest, real]) != real_dest:
        raise BoundaryError("目标路径越出安装目录: %s" % cur)
    return cur


def load_manifest(dest: str):
    """返回 (登记表 dict 或 None, 问题描述或 None)。"""
    p = os.path.join(dest, MANIFEST_NAME)
    if not os.path.lexists(p):
        return None, None
    if is_link_like(p) or not os.path.isfile(p):
        return None, "安装清单不是普通文件: %s" % p
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        files = data.get("files") if data.get("kind") == MANIFEST_KIND else None
        if not isinstance(files, dict) or not all(isinstance(v, str) for v in files.values()):
            return None, "安装清单格式无法识别（不是本工具写的）: %s" % p
        return files, None
    except (OSError, ValueError, AttributeError) as exc:
        return None, "安装清单无法解析: %s (%s)" % (p, exc)


def plan_install(source: str, dest: str, src_files: dict, owned: dict):
    """逐文件分类。返回 dict(create, update, same, conflicts)。"""
    create, update, same, conflicts, boundary = [], [], [], [], []
    for rel, h in sorted(src_files.items()):
        try:
            target = guard(dest, rel)
        except BoundaryError as exc:
            boundary.append((rel, str(exc)))  # R4-N3：链接/越界 → REFUSED rc1，不降级为 rc2 冲突
            continue
        # R4-N1：所需父目录位置被普通文件等非目录占用 → 冲突（预检阶段判出，不写任何文件）
        blocked, cur = None, dest
        for part in rel.split("/")[:-1]:
            cur = os.path.join(cur, part)
            if os.path.lexists(cur) and not os.path.isdir(cur):
                blocked = cur
                break
        if blocked:
            conflicts.append((rel, "所需目录位置被非目录占用: %s" % blocked))
            continue
        if not os.path.lexists(target):
            create.append(rel)
            continue
        if not os.path.isfile(target):
            conflicts.append((rel, "目标同名路径不是普通文件"))
            continue
        cur = sha256_file(target)
        if cur == h:
            same.append(rel)
        elif rel in owned and owned[rel] == cur:
            update.append(rel)  # 本技能写过且未被改动 → 可确认归属
        elif rel in owned:
            conflicts.append((rel, "技能文件已被他人修改（与安装清单登记哈希不同）"))
        else:
            conflicts.append((rel, "内容不同且无法确认归属（未在安装清单登记）"))
    return {"create": create, "update": update, "same": same, "conflicts": conflicts, "boundary": boundary}


def write_file(dest: str, rel: str, data: bytes) -> None:
    target = guard(dest, rel)
    parent = os.path.dirname(target)
    # 逐级建目录，每级建完再复核不是链接
    missing = []
    cur = parent
    while not os.path.lexists(cur):
        missing.append(cur)
        cur = os.path.dirname(cur)
    for d in reversed(missing):
        os.mkdir(d)
    guard(dest, rel)
    tmp = target + ".vbtmp-%d" % os.getpid()
    with open(tmp, "xb") as fh:
        fh.write(data)
    try:
        guard(dest, rel)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def main(argv):
    ap = argparse.ArgumentParser(description="安装 vibecoding 技能")
    ap.add_argument("--target", required=True, choices=sorted(TARGETS), help="目标平台目录约定")
    ap.add_argument("--scope", default="project", choices=["project", "user"])
    ap.add_argument("--project", default=".", help="scope=project 时的项目根")
    ap.add_argument("--path", help="显式指定技能根目录（覆盖平台默认约定）")
    ap.add_argument("--source", help="技能源目录（默认本脚本的上两级）")
    ap.add_argument("--force", action="store_true",
                    help="允许更新**可确认归属**的技能文件（不删除任何文件，不覆盖用户文件）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    here = os.path.dirname(os.path.abspath(__file__))
    source = os.path.abspath(args.source or os.path.join(here, "..", "vibecoding"))
    if not os.path.isfile(os.path.join(source, "SKILL.md")):
        print("ERROR: 源目录不含 SKILL.md: %s" % source)
        return 1

    root = args.path if args.path else TARGETS[args.target][args.scope]
    if args.scope == "user":
        base = os.path.join(os.path.expanduser("~"), root)
    else:
        base = os.path.join(os.path.abspath(args.project), root)
    dest = os.path.join(base, "vibecoding")

    print("== 安装 vibecoding 技能 ==")
    print("源      : %s" % source)
    print("目标    : %s" % dest)
    print("模式    : %s" % ("dry-run" if args.dry_run else "apply"))

    # R4-N5：源与目标真实位置相同或互相包含 → 拒绝（rc1，零写入）
    try:
        rs, rdst = os.path.realpath(source), os.path.realpath(dest)
        overlap = os.path.commonpath([rs, rdst]) in (rs, rdst)
    except ValueError:
        overlap = False
    if overlap:
        print("REFUSED: 源目录与目标目录重叠（相同或互相包含）: %s / %s" % (rs, rdst))
        print("== 结论: REFUSED（未写入任何文件，退出码 1）==")
        return 1
    try:
        src_files = source_files(source)
    except BoundaryError as exc:
        print("REFUSED: %s" % exc)
        print("== 结论: REFUSED（未写入任何文件，退出码 1）==")
        return 1

    if is_link_like(dest):
        print("REFUSED: 目标目录本身是符号链接/Junction/重解析点，拒绝跟随写入: %s" % dest)
        print("== 结论: REFUSED（未写入任何文件，退出码 1）==")
        return 1
    # R4-N4：project scope 下，项目根（不含）到目标目录之间任一分量是链接/重解析点 → 拒绝跟随（rc1）。
    # user scope 的 ~ 及其上层不在此检查范围（见 TODO R4-N4 说明）。
    if args.scope == "project":
        proj_abs = os.path.abspath(args.project)
        try:
            rel_dest = os.path.relpath(dest, proj_abs)
        except ValueError:
            rel_dest = ".."
        if not rel_dest.startswith(".."):
            cur = proj_abs
            for part in rel_dest.split(os.sep):
                cur = os.path.join(cur, part)
                if is_link_like(cur):
                    print("REFUSED: 安装路径分量是符号链接/Junction/重解析点，拒绝跟随写入: %s" % cur)
                    print("== 结论: REFUSED（未写入任何文件，退出码 1）==")
                    return 1
    # R5-N1：目标目录本身或其尚不存在的上层位置被普通文件等非目录占用 → 预检冲突（rc2，零写入，--force 不覆盖）
    cur = dest
    while not os.path.isdir(cur):
        if os.path.lexists(cur):
            print("  冲突: %s — 所需目录位置被非目录占用" % cur)
            print("REFUSED: 存在归属不明的冲突；--force 也不会覆盖。未写入任何文件。")
            print("== 结论: NEED_DECISION（未写入任何文件，退出码 2）==")
            return 2
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    exists = os.path.isdir(dest)
    owned, mproblem = (load_manifest(dest) if exists else (None, None))
    if mproblem:
        print("REFUSED: %s" % mproblem)
        print("  无法确认任何文件归属，拒绝更新。请人工检查该文件。")
        print("== 结论: NEED_DECISION（未写入任何文件，退出码 2）==")
        return 2
    has_manifest = owned is not None
    owned = owned or {}

    plan = plan_install(source, dest, src_files, owned)
    stale = sorted(r for r in owned if r not in src_files)
    print("已存在  : %s；安装清单: %s" % ("是" if exists else "否", "有" if has_manifest else "无"))
    print("计划    : 新增 %d / 更新(已确认归属) %d / 一致 %d / 冲突 %d"
          % (len(plan["create"]), len(plan["update"]), len(plan["same"]), len(plan["conflicts"])))
    for rel, why in plan["conflicts"][:20]:
        print("  冲突: %s — %s" % (rel, why))
    if stale:
        print("  旧版遗留的技能文件（源中已不存在，保留不删）: %s" % stale[:10])

    if plan["boundary"]:
        for rel, why in plan["boundary"][:20]:
            print("  链接/越界: %s — %s" % (rel, why))
        print("REFUSED: 安装路径中存在链接/重解析点或越界分量，拒绝跟随写入。")
        print("== 结论: REFUSED（未写入任何文件，退出码 1）==")
        return 1

    if plan["conflicts"]:
        print("REFUSED: 存在归属不明或被修改的冲突文件；--force 也不会覆盖它们。未写入任何文件。")
        print("  处置：人工确认这些文件后自行移走/合并，再重新安装。")
        print("== 结论: NEED_DECISION（退出码 2）==")
        return 2

    changes = plan["create"] + plan["update"]
    if exists and changes and not args.force:
        print("REFUSED: 目标存在且与源不同；确认更新可确认归属的技能文件请加 --force。")
        print("== 结论: NEED_DECISION（未写入任何文件，退出码 2）==")
        return 2

    need_manifest = not has_manifest or any(owned.get(r) != h for r, h in src_files.items())
    if args.dry_run:
        print("== dry-run 结束，未写盘（将写 %d 个文件%s）==" % (len(changes), "，并写安装清单" if need_manifest else ""))
        return 0

    written = []
    try:
        if not exists:
            os.makedirs(base, exist_ok=True)
            if is_link_like(dest):
                raise BoundaryError("目标目录在写入前变成了链接: %s" % dest)
            os.mkdir(dest)
        for rel in changes:
            with open(os.path.join(source, *rel.split("/")), "rb") as fh:
                data = fh.read()
            write_file(dest, rel, data)
            written.append(rel)
        if need_manifest or changes:
            files = dict(owned)
            files.update(src_files)
            payload = {"kind": MANIFEST_KIND, "version": 1,
                       "note": "由 install_skill.py 生成：登记本技能写入的文件；未登记的文件属于用户，安装器不会改动。",
                       "files": dict(sorted(files.items()))}
            write_file(dest, MANIFEST_NAME,
                       (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except (OSError, BoundaryError) as exc:
        print("ERROR: 安装中途失败: %s: %s" % (type(exc).__name__, exc))
        print("  已写入 %d 个文件（未回滚，未删除任何文件）: %s" % (len(written), written[:10]))
        print("== 结论: FAILED（安装未完成，退出码 1）==")
        return 1

    if changes:
        print("  已写入 %d 个文件（新增 %d，更新 %d）" % (len(changes), len(plan["create"]), len(plan["update"])))
    else:
        print("  内容一致，无需复制（幂等）")

    rc = 0
    ok_skill = os.path.isfile(os.path.join(dest, "SKILL.md"))
    vm = os.path.join(dest, "vendor", "vibecoding-standard", "tools", "verify_manifest.py")
    ok_std = None
    if os.path.isfile(vm):
        vrc, out, err = run([sys.executable, vm], cwd=os.path.dirname(os.path.dirname(vm)))
        ok_std = (vrc == 0)
        print("标准校验: rc=%d %s" % (vrc, [l for l in (out + err).strip().splitlines() if l.strip()][-1:]))
    else:
        print("标准校验: MISSING（未找到 vendor/vibecoding-standard/tools/verify_manifest.py）")
        ok_std = False
    print("入口校验: SKILL.md %s" % ("OK" if ok_skill else "MISSING"))
    if not ok_skill or not ok_std:
        rc = 1
    print("== %s ==" % ("结论: 安装完成（退出码 0）" if rc == 0 else "结论: FAILED（文件已写入但校验失败，不是完整安装，退出码 1）"))
    print("提示：WorkBuddy 类宿主在会话启动时注入技能列表，需**新开会话**才会发现新技能；Codex 会自动检测，未生效则重启。")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
