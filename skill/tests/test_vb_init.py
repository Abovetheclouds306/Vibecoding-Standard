# -*- coding: utf-8 -*-
"""vb_init.py 的 R1-FIX 正反测试（对应 Owner R1-FIX 授权第三节的九类输入）。

设计要点：
- 直接 import 被测模块并调用 main()，用 unittest.mock 注入"可控写入异常"，
  从而验证「回滚到与失败前完全一致」而不是只看退出码。
- 全部临时目录建立在系统临时目录下的独立子目录，跑完即清理；不写仓库。
- 断言以「文件树逐文件 sha256 完全一致」为判据，而不是只看返回码。
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
SKILL_ROOT = os.path.abspath(os.path.join(HERE, "..", "vibecoding"))
SCRIPT = os.path.join(SKILL_ROOT, "scripts", "vb_init.py")

_spec = importlib.util.spec_from_file_location("vb_init_under_test", SCRIPT)
vb_init = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb_init)


def snapshot(root: str) -> dict:
    """项目文件树快照：相对路径 -> sha256（跳过 .git）。"""
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        for f in fns:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            out[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vb_init.main(argv)
    return rc, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vbfix-")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write(self, rel, text):
        p = os.path.join(self.proj, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(p) else None
        with open(p, "wb") as fh:
            fh.write(text.encode("utf-8"))
        return p

    def read(self, rel):
        return open(os.path.join(self.proj, rel), "rb").read()

    def init(self, *extra):
        return run_main(["--project", self.proj, *extra])

    def git(self, *args):
        return subprocess.run(["git", "-C", self.proj, *args], capture_output=True)


class TestPositive(Base):
    """正常输入 -> 成功"""

    def test_fresh_empty_project(self):
        """1. 全新空项目首次初始化（F-1 原崩溃场景）"""
        before = snapshot(self.proj)
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        for rel in (".vibecoding/config.json", ".vibecoding/AGENTS.block.md",
                    ".vibecoding/evidence/_template.md", ".vibecoding/HANDOFF.md",
                    "AGENTS.md"):
            self.assertTrue(os.path.isfile(os.path.join(self.proj, rel)), rel)
        cfg = json.loads(self.read(".vibecoding/config.json").decode("utf-8"))
        self.assertEqual(cfg["standard_version"], "1.2.7")
        self.assertEqual(cfg["standard_release_commit"], vb_init.STANDARD_RELEASE)
        agents = self.read("AGENTS.md").decode("utf-8")
        self.assertEqual(agents.count("<!-- vibecoding:begin"), 1)
        self.assertEqual(agents.count("<!-- vibecoding:end -->"), 1)
        # 原先失败的路径必须留下可定位的 created 记录
        self.assertIn("config.json            created", out)
        self.assertNotEqual(before, snapshot(self.proj))

    def test_existing_agents_and_claude_md(self):
        """2. 已有 AGENTS.md 与 CLAUDE.md 的项目：只追加块，从不改 CLAUDE.md"""
        agents_orig = "# 既有约定\n\n- 仅标准库。\n"
        claude_orig = "# Claude 说明\n\n先跑测试。\n"
        self.write("AGENTS.md", agents_orig)
        self.write("CLAUDE.md", claude_orig)
        self.write("src/app.py", "print('hi')\n")
        claude_before = self.read("CLAUDE.md")

        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)

        agents = self.read("AGENTS.md").decode("utf-8")
        self.assertTrue(agents.startswith(agents_orig), "块外原文必须完全保留在前")
        self.assertEqual(agents.count("<!-- vibecoding:begin"), 1)
        self.assertEqual(agents.count("<!-- vibecoding:end -->"), 1)
        self.assertEqual(self.read("CLAUDE.md"), claude_before, "CLAUDE.md 不得被编辑")
        self.assertIn("需人工处理", out)
        self.assertIn("claude-md-and-agents-md", out)
        self.assertEqual(self.read("src/app.py"), b"print('hi')\n")

    def test_partial_existing_state_is_repaired(self):
        """3. 部分目标文件已存在：缺失的补齐，已存在且一致的保持 unchanged"""
        self.init("--apply")
        cfg_before = self.read(".vibecoding/config.json")
        os.remove(os.path.join(self.proj, ".vibecoding", "HANDOFF.md"))
        os.remove(os.path.join(self.proj, ".vibecoding", "evidence", "_template.md"))

        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".vibecoding", "HANDOFF.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".vibecoding", "evidence", "_template.md")))
        self.assertEqual(self.read(".vibecoding/config.json"), cfg_before, "initialized_at 应保留")

    def test_rerun_is_idempotent(self):
        """6. 初始化成功后重复执行：全部 unchanged，字节级零变化"""
        self.assertEqual(self.init("--apply")[0], 0)
        snap1 = snapshot(self.proj)
        cfg1 = self.read(".vibecoding/config.json")

        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.proj), snap1, "重复执行不得产生任何字节变化")
        self.assertEqual(self.read(".vibecoding/config.json"), cfg1, "不得刷新 initialized_at")
        self.assertNotIn("created", out.split("--- 步骤 ---")[1])
        self.assertNotIn("appended", out.split("--- 步骤 ---")[1])

    def test_rerun_after_failure_recovers(self):
        """7. 失败后再次初始化：应当成功"""
        before = snapshot(self.proj)
        real = vb_init._write_raw
        state = {"n": 0}

        def boom(path, data):
            state["n"] += 1
            if state["n"] == 3:
                raise OSError("injected failure")
            real(path, data)

        with mock.patch.object(vb_init, "_write_raw", boom):
            rc, out = self.init("--apply")
        self.assertNotEqual(rc, 0, out)
        self.assertEqual(snapshot(self.proj), before, "失败后必须回滚到失败前状态")

        rc2, out2 = self.init("--apply")
        self.assertEqual(rc2, 0, out2)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".vibecoding", "config.json")))


class TestNegative(Base):
    """无效输入 -> 明确失败（且写入前发现）"""

    def test_project_not_exist(self):
        """项目目录不存在"""
        rc, out = run_main(["--project", os.path.join(self.tmp, "nope"), "--apply"])
        self.assertEqual(rc, 1)
        self.assertIn("项目目录不存在", out)

    def test_project_is_a_file(self):
        """项目路径是文件"""
        p = os.path.join(self.tmp, "afile")
        open(p, "wb").write(b"x")
        rc, out = run_main(["--project", p, "--apply"])
        self.assertEqual(rc, 1)
        self.assertIn("项目目录不存在", out)   # 入口处即拒绝，未进入 preflight

    def test_vibecoding_is_a_file_conflict(self):
        """5(路径冲突). .vibecoding 是文件 -> 写入前拒绝，且不产生任何文件"""
        self.write(".vibecoding", "i am a file\n")
        before = snapshot(self.proj)
        rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("写入前检查未通过", out)
        self.assertEqual(snapshot(self.proj), before, "拒绝时不得写任何文件")
        self.assertFalse(os.path.exists(os.path.join(self.proj, "AGENTS.md")))

    def test_evidence_is_a_file_conflict(self):
        """.vibecoding/evidence 是文件 -> 写入前拒绝"""
        os.makedirs(os.path.join(self.proj, ".vibecoding"), exist_ok=True)
        self.write(".vibecoding/evidence", "not a dir\n")
        before = snapshot(self.proj)
        rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("evidence 已存在但不是目录", out)
        self.assertEqual(snapshot(self.proj), before)

    def test_agents_md_is_a_directory(self):
        """AGENTS.md 是目录 -> 写入前拒绝（不抛栈）"""
        os.makedirs(os.path.join(self.proj, "AGENTS.md"), exist_ok=True)
        before = snapshot(self.proj)
        rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("AGENTS.md 是目录", out)
        self.assertEqual(snapshot(self.proj), before)

    def test_dirty_worktree_guard(self):
        """脏工作区 + 需改 AGENTS.md -> 拒绝"""
        self.git("init")
        self.write("AGENTS.md", "# x\n")
        self.git("add", "-A")
        self.git("-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-m", "init")
        self.write("AGENTS.md", "# x\n\n- 用户新增\n")
        rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("--allow-dirty", out)


class TestRollback(Base):
    """可控中途异常 -> 不破坏原文件、不留半成品"""

    def test_midway_failure_rolls_back_everything(self):
        """4. 初始化过程中注入可控写入异常：文件树必须与失败前完全一致"""
        self.write("AGENTS.md", "# 原有约定\n")
        self.write("src/app.py", "x = 1\n")
        before = snapshot(self.proj)

        real = vb_init._write_raw
        state = {"n": 0}

        def boom(path, data):
            state["n"] += 1
            if state["n"] == 4:          # 第 4 次写入时炸
                raise OSError("injected disk error")
            real(path, data)

        with mock.patch.object(vb_init, "_write_raw", boom):
            rc, out = self.init("--apply")

        self.assertEqual(rc, 1, out)
        self.assertIn("已按逆序回滚", out)
        self.assertIn("OSError", out)
        self.assertIn("injected disk error", out)
        self.assertEqual(snapshot(self.proj), before, "回滚后必须与失败前逐字节一致")
        self.assertFalse(os.path.isdir(os.path.join(self.proj, ".vibecoding")),
                         "本次新建的 .vibecoding 应被清理")

    def test_failure_restores_agents_md(self):
        """失败发生在改 AGENTS.md 之后：AGENTS.md 必须恢复到原始字节"""
        orig = "# 原有约定\n\n- 只允许标准库\n"
        self.write("AGENTS.md", orig)
        real = vb_init._write_raw
        calls = {"n": 0}

        def boom(path, data):
            calls["n"] += 1
            real(path, data)
            if path.endswith("AGENTS.md"):
                raise OSError("fail after writing AGENTS.md")

        with mock.patch.object(vb_init, "_write_raw", boom):
            rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.read("AGENTS.md"), orig.encode("utf-8"),
                         "用户原有文件必须被还原，不得留下改到一半的内容")

    def test_rollback_skips_file_modified_by_others(self):
        """回滚不得覆盖"被其他进程改过"的文件（只跳过并报告）——直接验证 WriteJournal 契约"""
        target = os.path.join(self.proj, "AGENTS.md")
        self.write("AGENTS.md", "# 原\n")
        journal = vb_init.WriteJournal()
        journal.write(target, "# 原\n\n<!-- vibecoding:begin -->\n块\n<!-- vibecoding:end -->\n".encode("utf-8"))

        # 模拟别的进程在本进程写完后又改了它
        with open(target, "ab") as fh:
            fh.write("\n- 别的进程写的\n".encode("utf-8"))

        actions = journal.rollback()
        self.assertIn("Skipped(modified-by-others)", "\n".join(actions))
        self.assertIn("别的进程写的", open(target, encoding="utf-8").read(),
                      "他人改动必须保留，不得被回滚覆盖")

    def test_rollback_restores_and_removes(self):
        """回滚契约：已存在的文件被还原、新建的文件被删除、新建的空目录被清理"""
        keep = os.path.join(self.proj, "AGENTS.md")
        self.write("AGENTS.md", "原始内容\n")
        newf = os.path.join(self.proj, ".vibecoding", "config.json")
        journal = vb_init.WriteJournal()
        journal.mkdir(os.path.dirname(newf))
        journal.write(newf, b"{}\n")
        journal.write(keep, "原始内容\n追加块\n".encode("utf-8"))

        actions = journal.rollback()
        self.assertFalse(os.path.exists(newf), "新建文件应被删除")
        self.assertEqual(open(keep, "rb").read(), "原始内容\n".encode("utf-8"), "原有文件应被还原")
        self.assertFalse(os.path.isdir(os.path.dirname(newf)), "新建的空目录应被清理")
        self.assertTrue(any(a.startswith("Restored") for a in actions))
        self.assertTrue(any(a.startswith("Removed ") for a in actions))


class TestGitProtection(Base):
    """8. 初始化前后 Git 状态与文件哈希保护"""

    def test_git_status_and_hashes(self):
        self.git("init")
        self.write("AGENTS.md", "# 原有\n")
        self.write("src/app.py", "x = 1\n")
        self.git("add", "-A")
        self.git("-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-m", "init")
        before_status = self.git("status", "--porcelain").stdout

        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)

        after = self.git("status", "--porcelain").stdout.decode("utf-8")
        self.assertIn("AGENTS.md", after, "AGENTS.md 应显示为已修改")
        self.assertIn(".vibecoding/", after, "新增配置应显示为未跟踪")
        self.assertEqual(before_status, b"", "初始化前工作区应当是干净的")
        # 未涉及的业务文件不得进入改动集
        self.assertNotIn("src/app.py", after)


class TestScopeRedLines(unittest.TestCase):
    """保护范围自检：本修复不得越界改动"""

    def test_no_forbidden_artifacts(self):
        for rel in ("vb_audit.py", ".pre-commit-config.yaml"):
            hits = []
            for dp, _, fns in os.walk(SKILL_ROOT):
                for f in fns:
                    if f == rel:
                        hits.append(os.path.join(dp, f))
            self.assertEqual(hits, [], "不应新增 %s" % rel)

    def test_vendor_untouched_by_fix(self):
        """vendored 标准副本不得被本修复改动（比对 MANIFEST 自校验）"""
        vendor = os.path.join(SKILL_ROOT, "vendor", "vibecoding-standard")
        rc = subprocess.run([sys.executable, os.path.join(vendor, "tools", "verify_manifest.py")],
                            cwd=vendor, capture_output=True)
        self.assertEqual(rc.returncode, 0, (rc.stdout + rc.stderr).decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
