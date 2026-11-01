# -*- coding: utf-8 -*-
"""install_skill.py 的 INS-1 正反 / 边界 / 用户文件保护测试。

- 全部在系统临时目录下进行，绝不触碰真实技能安装目录（~/.claude、~/.agents、~/.cursor、WorkBuddy 等）：
  每个用例都用 --scope project --project <临时目录> --path <相对路径>。
- 被测脚本默认是本仓库的 skill/tools/install_skill.py；设置环境变量 VB_INSTALLER_UNDER_TEST
  可指向别的版本（用于判别力：对旧版 c08407d 安装器跑同一批用例，应出现 FAIL）。
- 无法创建符号链接/Junction 的系统上，相关用例 skipTest 并写明原因（记 NOT_RUN，不是 PASS）。
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.environ.get("VB_INSTALLER_UNDER_TEST") or os.path.abspath(
    os.path.join(HERE, "..", "tools", "install_skill.py"))
REAL_SKILL = os.path.abspath(os.path.join(HERE, "..", "vibecoding"))

_spec = importlib.util.spec_from_file_location("install_skill_under_test", INSTALLER)
inst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inst)

MANIFEST = ".vibecoding-install.json"


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def snapshot(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        for f in fns:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = sha(p)
    return out


def make_junction(link, target):
    if os.name != "nt":
        return False
    p = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
    return p.returncode == 0


def make_symlink(link, target):
    try:
        os.symlink(target, link, target_is_directory=os.path.isdir(target))
        return True
    except (OSError, NotImplementedError):
        return False


def remove_link(link):
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "rmdir", link], capture_output=True)
    if os.path.lexists(link):
        try:
            os.unlink(link)
        except OSError:
            pass


class Base(unittest.TestCase):
    VERIFY_RC = 0

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vbins-")
        self.addCleanup(self._cleanup)
        self.src = os.path.join(self.tmp, "src", "vibecoding")
        self.make_source({"SKILL.md": "skill v1\n", "references/a.md": "A1\n", "scripts/s.py": "print(1)\n"})
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)
        self.dest = os.path.join(self.proj, "skills", "vibecoding")
        self.outside = os.path.join(self.tmp, "outside")
        os.makedirs(self.outside)
        self.write(os.path.join(self.outside, "keep.txt"), "user data outside\n")

    def _cleanup(self):
        # 先拆链接再删，避免清理时跟随链接删到外部
        for dp, dns, _ in os.walk(self.tmp):
            for d in dns:
                p = os.path.join(dp, d)
                if inst_is_link(p):
                    remove_link(p)
        shutil.rmtree(self.tmp, True)

    def write(self, p, text):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(text.encode("utf-8"))

    def make_source(self, files):
        if os.path.isdir(self.src):
            shutil.rmtree(self.src)
        for rel, text in files.items():
            self.write(os.path.join(self.src, *rel.split("/")), text)
        self.write(os.path.join(self.src, "vendor", "vibecoding-standard", "tools", "verify_manifest.py"),
                   "import sys\nprint('stub verify')\nsys.exit(%d)\n" % self.VERIFY_RC)

    def install(self, *extra, source=None):
        argv = ["--target", "claude-code", "--scope", "project", "--project", self.proj,
                "--path", "skills", "--source", source or self.src, *extra]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = inst.main(argv)
        return rc, buf.getvalue()


def inst_is_link(p):
    try:
        st = os.lstat(p)
    except OSError:
        return False
    import stat as _s
    return _s.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x400)


class TestInstallPositive(Base):
    def test_fresh_install_writes_files_and_ownership_manifest(self):
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        self.assertEqual(sha(os.path.join(self.dest, "SKILL.md")), sha(os.path.join(self.src, "SKILL.md")))
        mp = os.path.join(self.dest, MANIFEST)
        self.assertTrue(os.path.isfile(mp), "必须写安装清单以便后续确认归属")
        with open(mp, encoding="utf-8") as fh:
            files = json.load(fh)["files"]
        self.assertEqual(files["references/a.md"], sha(os.path.join(self.src, "references", "a.md")))
        self.assertNotIn(MANIFEST, files)

    def test_rerun_is_idempotent(self):
        self.assertEqual(self.install()[0], 0)
        before = snapshot(self.dest)
        rc, out = self.install()
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.dest), before)
        rc, out = self.install("--force")
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.dest), before)

    def test_dry_run_writes_nothing(self):
        rc, out = self.install("--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertFalse(os.path.exists(self.dest))

    def test_real_skill_install_into_temp_then_idempotent(self):
        rc, out = self.install(source=REAL_SKILL)
        self.assertEqual(rc, 0, out)
        before = snapshot(self.dest)
        rc, out = self.install(source=REAL_SKILL)
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.dest), before)


class TestUserFileProtection(Base):
    def upgrade_source(self):
        self.make_source({"SKILL.md": "skill v2\n", "references/a.md": "A2\n", "scripts/s.py": "print(1)\n",
                          "references/new.md": "N\n"})

    def test_force_update_keeps_user_files_and_updates_owned(self):
        self.assertEqual(self.install()[0], 0)
        user1 = os.path.join(self.dest, "my-notes.md")
        user2 = os.path.join(self.dest, "references", "user-extra.md")
        self.write(user1, "mine\n")
        self.write(user2, "mine too\n")
        self.upgrade_source()
        rc, out = self.install("--force")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(user1), "--force 不得删除用户新增文件")
        self.assertTrue(os.path.isfile(user2), "--force 不得删除用户新增文件（子目录）")
        with open(os.path.join(self.dest, "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "skill v2\n")
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "references", "new.md")))

    def test_without_force_differs_refuses_with_2_and_writes_nothing(self):
        self.assertEqual(self.install()[0], 0)
        before = snapshot(self.dest)
        self.upgrade_source()
        rc, out = self.install()
        self.assertEqual(rc, 2, out)
        self.assertEqual(snapshot(self.dest), before)

    def test_modified_owned_file_is_conflict_even_with_force(self):
        self.assertEqual(self.install()[0], 0)
        self.write(os.path.join(self.dest, "references", "a.md"), "user edited\n")
        before = snapshot(self.dest)
        self.upgrade_source()
        rc, out = self.install("--force")
        self.assertEqual(rc, 2, out)
        self.assertEqual(snapshot(self.dest), before, "冲突时一个文件也不得写")
        self.assertNotIn("安装完成", out)

    def test_legacy_dir_without_manifest_differs_is_conflict(self):
        os.makedirs(self.dest)
        self.write(os.path.join(self.dest, "SKILL.md"), "someone else's skill\n")
        self.write(os.path.join(self.dest, "extra.txt"), "x\n")
        before = snapshot(self.dest)
        rc, out = self.install("--force")
        self.assertEqual(rc, 2, out)
        self.assertEqual(snapshot(self.dest), before)

    def test_corrupt_manifest_refuses(self):
        self.assertEqual(self.install()[0], 0)
        self.write(os.path.join(self.dest, MANIFEST), "{not json")
        self.upgrade_source()
        before = snapshot(self.dest)
        rc, out = self.install("--force")
        self.assertEqual(rc, 2, out)
        self.assertEqual(snapshot(self.dest), before)

    def test_stale_owned_file_not_deleted(self):
        self.assertEqual(self.install()[0], 0)
        self.make_source({"SKILL.md": "skill v2\n", "references/a.md": "A1\n"})
        rc, out = self.install("--force")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "scripts", "s.py")), "安装器不删除任何文件")

    def test_directory_in_place_of_file_is_conflict(self):
        self.assertEqual(self.install()[0], 0)
        p = os.path.join(self.dest, "scripts", "s.py")
        os.remove(p)
        os.makedirs(p)
        self.write(os.path.join(p, "inner.txt"), "u\n")
        self.upgrade_source()
        rc, out = self.install("--force")
        self.assertEqual(rc, 2, out)
        self.assertTrue(os.path.isfile(os.path.join(p, "inner.txt")))


class TestLinksAndBoundary(Base):
    def _link(self, link, target):
        if make_junction(link, target) or make_symlink(link, target):
            return
        self.skipTest("NOT_RUN: 本系统无法创建 Junction/符号链接（%s）" % os.name)

    def test_dest_itself_is_link_refused_and_outside_untouched(self):
        os.makedirs(os.path.dirname(self.dest), exist_ok=True)
        self._link(self.dest, self.outside)
        before = snapshot(self.outside)
        try:
            rc, out = self.install("--force")
        except Exception as exc:  # 旧实现会在 rmtree 处抛异常 → 视为不满足契约
            self.fail("安装器抛出未处理异常: %r" % exc)
        self.assertEqual(rc, 1, out)
        self.assertEqual(snapshot(self.outside), before)
        self.assertTrue(inst_is_link(self.dest), "不得删除用户的链接")

    def test_inner_dir_link_not_followed_nor_deleted(self):
        self.assertEqual(self.install()[0], 0)
        refs = os.path.join(self.dest, "references")
        shutil.rmtree(refs)
        self.write(os.path.join(self.outside, "a.md"), "outside A\n")
        self._link(refs, self.outside)
        before = snapshot(self.outside)
        self.make_source({"SKILL.md": "skill v2\n", "references/a.md": "A2\n", "scripts/s.py": "print(1)\n"})
        try:
            rc, out = self.install("--force")
        except Exception as exc:
            self.fail("安装器抛出未处理异常: %r" % exc)
        self.assertEqual(rc, 1, out)  # R4-N3：链接分量按文档为 REFUSED rc1
        self.assertEqual(snapshot(self.outside), before, "不得经链接写到安装目录之外")
        self.assertTrue(inst_is_link(refs), "不得删除用户的链接")

    def test_file_symlink_in_dest_refused(self):
        self.assertEqual(self.install()[0], 0)
        p = os.path.join(self.dest, "SKILL.md")
        os.remove(p)
        tgt = os.path.join(self.outside, "keep.txt")
        if not make_symlink(p, tgt):
            self.skipTest("NOT_RUN: 本系统不允许创建文件符号链接（Windows 需开发者模式/管理员）")
        before = snapshot(self.outside)
        self.make_source({"SKILL.md": "skill v2\n", "references/a.md": "A1\n", "scripts/s.py": "print(1)\n"})
        rc, out = self.install("--force")
        self.assertEqual(rc, 1, out)  # R4-N3
        self.assertEqual(snapshot(self.outside), before)


class TestR4N1FileOccupiesDir(Base):
    """R4-N1：用户普通文件占据技能需要的目录位置。"""

    def _occupy(self):
        os.makedirs(self.dest, exist_ok=True)
        self.write(os.path.join(self.dest, "scripts"), "user file named scripts\n")

    def test_no_force_reports_conflict_and_writes_nothing(self):
        self._occupy()
        before = snapshot(self.dest)
        rc, out = self.install()
        self.assertEqual(rc, 2, out)
        self.assertIn("冲突: scripts/s.py", out)
        self.assertEqual(snapshot(self.dest), before)

    def test_force_refuses_rc2_and_writes_nothing(self):
        self._occupy()
        before = snapshot(self.dest)
        rc, out = self.install("--force")
        self.assertEqual(rc, 2, out)
        self.assertIn("冲突: scripts/s.py", out)
        self.assertEqual(snapshot(self.dest), before, "冲突时一个文件也不得写（含 --force）")
        self.assertNotIn("安装完成", out)

    def test_after_install_file_replacing_dir_is_conflict(self):
        self.assertEqual(self.install()[0], 0)
        shutil.rmtree(os.path.join(self.dest, "scripts"))
        self.write(os.path.join(self.dest, "scripts"), "user\n")
        self.make_source({"SKILL.md": "skill v2\n", "references/a.md": "A1\n", "scripts/s.py": "print(1)\n"})
        before = snapshot(self.dest)
        rc, out = self.install("--force")
        self.assertEqual(rc, 2, out)
        self.assertEqual(snapshot(self.dest), before)



class R7Helper(Base):
    def run_argv(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = inst.main(argv)
        return rc, buf.getvalue()

class TestR4N4AncestorLink(R7Helper):
    def test_R4N4_ancestor_junction_refused(self):
        if not make_junction(os.path.join(self.proj, "skills"), self.outside):
            self.skipTest("NOT_RUN: 无法创建 Junction")
        before = snapshot(self.outside)
        for extra in ((), ("--force",)):
            rc, out = self.install(*extra)
            self.assertEqual(rc, 1, out)
            self.assertEqual(snapshot(self.outside), before, "不得经上层 Junction 写到项目外")


class TestR4N5SourceDestOverlap(R7Helper):
    def test_R4N5_dest_equals_source(self):
        same = os.path.join(self.proj, "skills", "vibecoding")
        shutil.copytree(self.src, same)
        before = snapshot(same)
        rc, out = self.install("--force", source=same)
        self.assertEqual(rc, 1, out)
        self.assertEqual(snapshot(same), before)

    def test_R4N5_dest_inside_source(self):
        before = snapshot(self.src)
        rc, out = self.run_argv(["--target", "claude-code", "--scope", "project", "--project", self.src,
                                 "--path", "nested", "--source", self.src])
        self.assertEqual(rc, 1, out)
        self.assertEqual(snapshot(self.src), before)

    def test_R4N5_source_inside_dest(self):
        inner = os.path.join(self.dest, "sub", "vibecoding")
        shutil.copytree(self.src, inner)
        before = snapshot(self.proj)
        rc, out = self.install("--force", source=inner)
        self.assertEqual(rc, 1, out)
        self.assertEqual(snapshot(self.proj), before)


class TestR5N1PathOccupiedByFile(R7Helper):
    def _check(self, run):
        before = snapshot(self.proj)
        for extra in ((), ("--force",)):
            rc, out = run(*extra)
            self.assertEqual(rc, 2, out)
            self.assertIn("冲突", out)
            self.assertEqual(snapshot(self.proj), before, "冲突时必须零写入")

    def test_R5N1_parent_of_dest_is_file(self):
        self.write(os.path.join(self.proj, "skills"), "user file\n")
        self._check(self.install)

    def test_R5N1_dest_itself_is_file(self):
        self.write(self.dest, "user file\n")
        self._check(self.install)

    def test_R5N1_default_layout_dot_claude_is_file(self):
        self.write(os.path.join(self.proj, ".claude"), "user file\n")
        self._check(lambda *e: self.run_argv(["--target", "claude-code", "--scope", "project",
                                              "--project", self.proj, "--source", self.src, *e]))


class TestR4N10ManifestKeysAndInnerLink(R7Helper):
    def test_R4N10_manifest_invalid_keys_not_carried(self):
        self.assertEqual(self.install()[0], 0)
        mp = os.path.join(self.dest, MANIFEST)
        with open(mp, encoding="utf-8") as fh:
            data = json.load(fh)
        data["files"]["../evil.txt"] = "0" * 64
        data["files"]["C:/abs.txt"] = "0" * 64
        with open(mp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        self.make_source({"SKILL.md": "skill v2\n", "references/a.md": "A1\n", "scripts/s.py": "print(1)\n"})
        rc, out = self.install("--force")
        self.assertEqual(rc, 0, out)
        with open(mp, encoding="utf-8") as fh:
            files = json.load(fh)["files"]
        self.assertNotIn("../evil.txt", files)
        self.assertNotIn("C:/abs.txt", files)

    def test_R4N10_inner_junction_into_dest_refused(self):
        self.assertEqual(self.install()[0], 0)
        sp = os.path.join(self.dest, "scripts")
        shutil.rmtree(sp)
        if not make_junction(sp, os.path.join(self.dest, "references")):
            self.skipTest("NOT_RUN: 无法创建 Junction")
        self.make_source({"SKILL.md": "skill v1\n", "references/a.md": "A1\n", "scripts/s.py": "print(2)\n",
                          "scripts/a.md": "X\n"})
        before = snapshot(os.path.join(self.dest, "references"))
        rc, out = self.install("--force")
        self.assertEqual(rc, 1, out)
        self.assertEqual(snapshot(os.path.join(self.dest, "references")), before)


class TestFailureHonesty(Base):
    def test_write_failure_reports_incomplete(self):
        def boom(*a, **k):
            raise OSError("injected write failure")
        with mock.patch.object(os, "replace", boom), mock.patch.object(shutil, "copy2", boom):
            try:
                rc, out = self.install()
            except Exception as exc:
                self.fail("写入失败应被报告为非零退出码而不是抛异常: %r" % exc)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("安装完成", out)
        self.assertIn("FAILED", out)


class TestVerifyFailure(Base):
    VERIFY_RC = 1

    def test_verify_failure_is_not_reported_as_install_complete(self):
        rc, out = self.install()
        self.assertEqual(rc, 1, out)
        self.assertNotIn("安装完成", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
