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
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(HERE, "..", "vibecoding"))
SCRIPT = os.path.join(SKILL_ROOT, "scripts", "vb_init.py")
VENDOR_SRC = os.path.join(SKILL_ROOT, "vendor", "vibecoding-standard")

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
            with open(p, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


def run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vb_init.main(argv)
    return rc, buf.getvalue()


# ------------------------------------------------ R2-FIX 共用工具
def block_of(project):
    """取 AGENTS.md 里的标记块原文（无块返回空串）。"""
    p = os.path.join(project, "AGENTS.md")
    if not os.path.isfile(p):
        return ""
    with open(p, encoding="utf-8") as fh:
        text = fh.read()
    i = text.find(vb_init.BEGIN)
    j = text.find(vb_init.END, i)
    return text[i:j + len(vb_init.END)] if i >= 0 and j >= 0 else ""


def declared_paths(project, block):
    """抽出块里「真值源 / 规范位置 / 解算」三类行上的反引号路径并解析成绝对路径。"""
    out = []
    for line in block.splitlines():
        if not any(k in line for k in ("真值源", "规范位置", "解算")):
            continue
        for tok in re.findall(r"`([^`]+)`", line):
            if "/" not in tok and "\\" not in tok:
                continue
            p = tok.replace("\\", "/").rstrip("/")
            if not os.path.isabs(p):
                p = os.path.join(project, p)
            out.append(os.path.normpath(p))
    return out


def bullet_titles(text):
    return re.findall(r"^- \*\*([^*]+)\*\*", text, flags=re.M)


def junction(link, target):
    """创建目录 Junction（仅 Windows）。成功返回 True。"""
    if os.name != "nt":
        return False
    os.makedirs(os.path.dirname(link), exist_ok=True)
    p = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
    return p.returncode == 0


def rmdir_link(link):
    if os.name == "nt" and os.path.exists(link):
        subprocess.run(["cmd", "/c", "rmdir", link], capture_output=True)


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
        with open(os.path.join(self.proj, rel), "rb") as fh:
            return fh.read()

    def init(self, *extra):
        return run_main(["--project", self.proj, *extra])

    def git(self, *args):
        # stdin 必须断开：否则 git 一旦想读提示（凭据/确认）会永久阻塞整轮测试。
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "echo"
        return subprocess.run(["git", "-C", self.proj, *args],
                              capture_output=True, stdin=subprocess.DEVNULL,
                              env=env, timeout=120)


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
        with open(p, "wb") as fh:
            fh.write(b"x")
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
        """失败发生在 AGENTS.md 已提交之后：AGENTS.md 必须恢复到原始字节

        R2-N1 修复后写入改为「同目录临时文件 + 原子替换」，因此「写完才失败」的注入点
        从 _write_raw 移到提交点 _replace —— 否则注入永远打不到真实目标文件，测试会失去判别力。
        """
        orig = "# 原有约定\n\n- 只允许标准库\n"
        self.write("AGENTS.md", orig)
        real = vb_init._replace
        seen = {"fired": False, "on_disk": None}

        def boom(tmp, dst):
            real(tmp, dst)
            if dst.endswith("AGENTS.md") and not seen["fired"]:
                seen["fired"] = True
                with open(dst, "rb") as fh:
                    seen["on_disk"] = fh.read()     # 证明"真的写过"，而不是根本没改
                raise OSError("fail after committing AGENTS.md")

        with mock.patch.object(vb_init, "_replace", boom):
            rc, out = self.init("--apply")
        self.assertTrue(seen["fired"], "注入点未被触发，测试无判别力")
        self.assertNotEqual(seen["on_disk"], orig.encode("utf-8"),
                            "提交阶段 AGENTS.md 应当已被改过，否则本用例不构成回滚证据")
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
        with open(target, encoding="utf-8") as fh:
            self.assertIn("别的进程写的", fh.read(),
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
        with open(keep, "rb") as fh:
            self.assertEqual(fh.read(), "原始内容\n".encode("utf-8"), "原有文件应被还原")
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


class TestF2VendorLocating(Base):
    """F-2：注入块必须指向真实存在、可读的规范位置；不依赖 Agent 主动调用 Skill。"""

    PROJ_SUB = ".claude/skills/vibecoding/vendor/vibecoding-standard"

    def install_vendor_into_project(self):
        dst = os.path.join(self.proj, *self.PROJ_SUB.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copytree(VENDOR_SRC, dst,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        return dst

    def cfg(self):
        return json.loads(self.read(".vibecoding/config.json").decode("utf-8"))

    def resolve_cfg_path(self, rel):
        p = rel.replace("\\", "/")
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(self.proj, p))

    def test_external_install_block_paths_all_exist(self):
        """技能在项目外：块内每个声明路径都必须真实存在，且不得再出现那个从不创建的路径"""
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        blk = block_of(self.proj)
        self.assertNotIn(".vibecoding/vendor", blk, "块内不得再出现 .vibecoding/vendor/...")
        paths = declared_paths(self.proj, blk)
        self.assertTrue(paths, "块内应至少声明一个可解析路径")
        for p in paths:
            self.assertTrue(os.path.exists(p), "块内声明的路径必须存在: %s" % p)
        self.assertIn("standard_vendor_path", blk, "块必须点名字段，而非只说「读 config.json」")

    def test_agent_can_read_standard_via_project_entry_only(self):
        """只靠 AGENTS.md → config.json → standard_vendor_path 就能读到规范正文"""
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        cfg = self.cfg()
        doc = os.path.join(self.resolve_cfg_path(cfg["standard_vendor_path"]),
                           "AI_PROJECT_STANDARD.md")
        self.assertTrue(os.path.isfile(doc), "配置给出的规范正文必须可读: %s" % doc)
        with open(doc, encoding="utf-8") as fh:
            body = fh.read()
        self.assertGreater(len(body), 1000, "规范正文不应是空壳")
        self.assertIn("Vibecoding", body)

    def test_in_project_install_uses_relative_path_and_survives_move(self):
        """项目内安装：记相对路径；项目整体移动后仍可解析"""
        v = self.install_vendor_into_project()
        rc, out = self.init("--apply", "--standard", v)
        self.assertEqual(rc, 0, out)
        rel = self.cfg()["standard_vendor_path"]
        self.assertFalse(os.path.isabs(rel), "项目内安装应记相对路径，否则移动即失效: %s" % rel)
        self.assertTrue(rel.startswith(".claude/"), rel)

        moved = self.proj + "-moved"
        shutil.move(self.proj, moved)
        self.addCleanup(shutil.rmtree, moved, True)
        doc = os.path.normpath(os.path.join(moved, rel, "AI_PROJECT_STANDARD.md"))
        self.assertTrue(os.path.isfile(doc), "项目移动后规范定位必须仍有效: %s" % doc)
        # 块内的相对路径同样应随移动有效
        for p in declared_paths(moved, block_of(moved)):
            self.assertTrue(os.path.exists(p), "移动后块内路径失效: %s" % p)

    def test_external_install_marks_machine_dependency(self):
        """项目外安装：必须记绝对路径，并在块内如实标注失效条件"""
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        p = self.cfg()["standard_vendor_path"]
        self.assertTrue(os.path.isabs(p), "项目外 vendor 不应写成相对路径（会越出项目且随目录深度失效）")
        self.assertFalse(p.split("/")[0] in ("..",), p)
        blk = block_of(self.proj)
        self.assertIn("换机器", blk)
        self.assertIn("重定位", blk)

    def test_vendor_missing_reports_access_gap_and_writes_nothing(self):
        """技能卸载 / vendor 定位失败：明确报接入缺失，且不写任何文件"""
        before = snapshot(self.proj)
        with mock.patch.object(vb_init, "find_standard",
                               return_value=(None, "注入：无可用 vendor")):
            rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("接入缺失", out)
        self.assertEqual(snapshot(self.proj), before, "接入缺失时不得写任何文件")
        self.assertFalse(os.path.exists(os.path.join(self.proj, "AGENTS.md")))

    def test_vendor_standard_doc_unreadable_refuses(self):
        """正文为空 / 不可读：不得写指向它的注入块"""
        v = self.install_vendor_into_project()
        with open(os.path.join(v, "AI_PROJECT_STANDARD.md"), "wb") as fh:
            fh.write(b"")
        before = snapshot(self.proj)
        rc, out = self.init("--apply", "--standard", v)
        self.assertEqual(rc, 1, out)
        self.assertIn("规范接入缺失", out)
        self.assertEqual(snapshot(self.proj), before)

    def test_manifest_missing_refuses(self):
        """缺 MANIFEST.sha256：无法证明与签收版本一致 ⇒ 拒绝"""
        v = self.install_vendor_into_project()
        os.remove(os.path.join(v, "MANIFEST.sha256"))
        rc, out = self.init("--apply", "--standard", v)
        self.assertEqual(rc, 1, out)
        self.assertIn("MANIFEST.sha256", out)

    def test_vendor_is_not_copied_into_project(self):
        """不强制复制整份规范进项目（否则会出现第二套规则副本）"""
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        self.assertFalse(
            os.path.isdir(os.path.join(self.proj, ".vibecoding", "vendor")),
            "不得把整份 vendor 复制进项目")

    def test_assets_block_mirrors_generated_block(self):
        """资产副本不得与生成的块结构脱节（尤其不得留着旧路径）"""
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        with open(os.path.join(SKILL_ROOT, "assets", "AGENTS.block.md"), encoding="utf-8") as fh:
            asset = fh.read()
        self.assertNotIn(".vibecoding/vendor", asset, "资产副本不得再指向不存在的路径")
        self.assertEqual(bullet_titles(asset), bullet_titles(block_of(self.proj)),
                         "资产副本与生成块的最低动作集必须一致")


class TestF5ExitCode(Base):
    """F-5：退出码 / 横幅 / 动作记录三者必须描述同一件事。"""

    MUT = "**证据（人工改动）**"

    def setUp(self):
        super().setUp()
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        p = os.path.join(self.proj, "AGENTS.md")
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        with open(p, "wb") as fh:
            fh.write(txt.replace("**证据**", self.MUT, 1).encode("utf-8"))
        self.assertEqual(self.init("--apply")[0], 2, "前置条件：块应处于 differs 状态")

    def agents_text(self):
        with open(os.path.join(self.proj, "AGENTS.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_differs_without_authorization_returns_2(self):
        rc, out = self.init("--apply")
        self.assertEqual(rc, 2, out)
        self.assertIn("skipped(需 --update-block)", out)
        self.assertIn("NEED_DECISION", out)
        self.assertIn("人工改动", self.agents_text(), "未授权时不得改动块内容")

    def test_update_block_success_returns_0_and_banner_matches(self):
        rc, out = self.init("--apply", "--update-block")
        self.assertEqual(rc, 0, out)
        self.assertIn("block_updated", out)
        self.assertIn("OK（标记块已更新）", out)
        self.assertNotIn("NEED_DECISION", out)
        now = self.agents_text()
        self.assertNotIn("人工改动", now, "授权后应真的更新块")
        self.assertEqual(now.count("<!-- vibecoding:begin"), 1)

    def test_update_block_write_failure_returns_nonzero(self):
        real = vb_init._replace

        def boom(tmp, dst):
            if dst.endswith("AGENTS.md"):
                raise OSError("injected replace failure")
            real(tmp, dst)

        with mock.patch.object(vb_init, "_replace", boom):
            rc, out = self.init("--apply", "--update-block")
        self.assertEqual(rc, 1, out)
        self.assertNotIn("block_updated", out, "写入失败不得记录为成功")
        self.assertIn("人工改动", self.agents_text(), "失败时不得冒充已更新")

    def test_dry_run_differs_returns_2(self):
        rc, out = self.init()
        self.assertEqual(rc, 2, out)
        self.assertIn("would_differs", out)

    def test_json_output_rc_matches_process_rc(self):
        rc, out = self.init("--apply", "--update-block", "--json")
        self.assertEqual(rc, 0, out)
        data = json.loads(out)
        self.assertEqual(data["rc"], 0)
        self.assertTrue(data["block_updated"])
        self.assertFalse(data["needs_decision"])


class TestN1WriteJournal(Base):
    """R2-N1：先登记后写 + 单条原子写 + 残留如实报告。"""

    def test_half_write_never_truncates_target(self):
        """注入「只写一半就报错」：目标文件必须毫发无损（R2-N1 的最小复现）"""
        target = self.write("AGENTS.md", "# 原\n" + "- 约定\n" * 20)
        orig = self.read("AGENTS.md")

        def half(path, data):
            with open(path, "wb") as fh:
                fh.write(data[: len(data) // 2])
            raise OSError(28, "No space left on device")

        journal = vb_init.WriteJournal(root=self.proj)
        with mock.patch.object(vb_init, "_write_raw", half):
            with self.assertRaises(OSError):
                journal.write(target, orig[:67] + b"- new\n")
        self.assertEqual(self.read("AGENTS.md"), orig, "目标文件不得被截断")
        self.assertEqual(len(journal.entries), 1, "写入前必须已登记意图")
        self.assertEqual(journal.entries[0]["state"], "aborted")
        self.assertEqual(journal.residuals, [])
        # 临时文件不得残留
        leftovers = [f for f in os.listdir(self.proj) if f.startswith(".vb-w-")]
        self.assertEqual(leftovers, [], "临时文件应被清理: %s" % leftovers)

    def test_intent_is_registered_before_content_is_written(self):
        """登记顺序：写入抛错时条目已经在册（否则回滚无从下手）"""
        target = self.write("AGENTS.md", "# 原\n")
        seen = {}

        def boom(path, data):
            raise OSError(5, "I/O error")

        journal = vb_init.WriteJournal(root=self.proj)
        with mock.patch.object(vb_init, "_write_raw", boom):
            with self.assertRaises(OSError):
                journal.write(target, b"new content\n")
            seen["n"] = len(journal.entries)
        self.assertEqual(seen["n"], 1, "失败时条目必须已登记")
        self.assertEqual(self.read("AGENTS.md"), "# 原\n".encode("utf-8"))

    def test_restore_failure_reports_residual_not_false_claim(self):
        """还原也失败：必须输出 ResidualRisk，且不得宣称「已回滚」"""
        self.write("AGENTS.md", "# 原\n" + "- 约定\n" * 20)
        real = vb_init._atomic_write

        def bad(path, data):
            if path.replace("\\", "/").endswith("AGENTS.md"):
                with open(path, "wb") as fh:
                    fh.write(data[: max(1, len(data) // 2)])
                raise OSError(28, "disk full")
            real(path, data)

        with mock.patch.object(vb_init, "_atomic_write", bad):
            rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("ResidualRisk", out)
        self.assertIn("回滚不完整", out)
        self.assertNotIn("（已回滚，退出码 1）", out,
                         "有残留时不得打印「已回滚」")
        self.assertIn("实际残留", out)

    def test_rollback_marks_untouched_entries_unchanged(self):
        """写入已中止（目标未被改动）的条目，回滚应记为 Unchanged 而非 Restored"""
        target = self.write("AGENTS.md", "# 原\n")
        journal = vb_init.WriteJournal(root=self.proj)
        journal.entries.append({
            "path": target, "existed": True, "original": "# 原\n".encode("utf-8"),
            "written": "# 别的\n".encode("utf-8"), "step": "t", "state": "aborted",
        })
        actions = journal.rollback()
        self.assertIn("Unchanged", "\n".join(actions))
        self.assertEqual(self.read("AGENTS.md"), "# 原\n".encode("utf-8"))

    def test_modified_by_others_still_skipped(self):
        """他人改动仍不得被覆盖（写入改为原子替换后该性质必须保留）"""
        target = self.write("AGENTS.md", "# 原\n")
        journal = vb_init.WriteJournal(root=self.proj)
        journal.write(target, "# 原\n\n- 本进程\n".encode("utf-8"))
        with open(target, "ab") as fh:
            fh.write("\n- 他人\n".encode("utf-8"))
        actions = journal.rollback()
        self.assertIn("Skipped(modified-by-others)", "\n".join(actions))
        with open(target, encoding="utf-8") as fh:
            self.assertIn("他人", fh.read())


@unittest.skipUnless(os.name == "nt", "Junction 场景仅 Windows")
class TestN2Boundary(Base):
    """R2-N2：预检后目标被替换为重解析点 ⇒ 拒绝写入，不得写到项目外。"""

    def ext_dir(self):
        p = os.path.join(self.tmp, "outside")
        os.makedirs(p, exist_ok=True)
        return p

    def test_swap_after_preflight_is_refused(self):
        """R2 的原始负例：预检通过后、首次写入前替换为外部 Junction"""
        ext = self.ext_dir()
        real = vb_init.preflight
        state = {"ok": False}

        def evil(project, plan):
            res = real(project, plan)
            state["ok"] = junction(os.path.join(project, ".vibecoding"), ext)
            return res

        try:
            with mock.patch.object(vb_init, "preflight", evil):
                rc, out = self.init("--apply")
        finally:
            rmdir_link(os.path.join(self.proj, ".vibecoding"))
        self.assertTrue(state["ok"], "Junction 未创建，用例无效")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("越界", out)
        self.assertEqual(os.listdir(ext), [], "项目外不得写入任何文件")

    def test_preexisting_external_junction_is_refused(self):
        ext = self.ext_dir()
        self.assertTrue(junction(os.path.join(self.proj, ".vibecoding"), ext))
        self.addCleanup(rmdir_link, os.path.join(self.proj, ".vibecoding"))
        rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertIn("写入前检查未通过", out)
        self.assertEqual(os.listdir(ext), [])

    def test_drift_of_existing_dir_is_detected(self):
        """预检时是真实目录、预检后被换成项目内的 Junction ⇒ 也必须识别为漂移"""
        os.makedirs(os.path.join(self.proj, ".vibecoding"))
        decoy = os.path.join(self.proj, "decoy")
        os.makedirs(decoy)
        real = vb_init.preflight
        state = {"ok": False}

        def evil(project, plan):
            res = real(project, plan)
            shutil.rmtree(os.path.join(project, ".vibecoding"), ignore_errors=True)
            state["ok"] = junction(os.path.join(project, ".vibecoding"), decoy)
            return res

        try:
            with mock.patch.object(vb_init, "preflight", evil):
                rc, out = self.init("--apply")
        finally:
            rmdir_link(os.path.join(self.proj, ".vibecoding"))
        self.assertTrue(state["ok"], "Junction 未创建，用例无效")
        self.assertEqual(rc, 1, out)
        self.assertIn("预检后", out)
        self.assertEqual(os.listdir(decoy), [], "项目内诱饵目录也不得被写入")

    def test_rollback_does_not_follow_replaced_path(self):
        """回滚不得跟随被替换的路径去删改项目外数据"""
        journal = vb_init.WriteJournal(root=self.proj)
        journal.mkdir(os.path.join(self.proj, ".vibecoding"))
        journal.write(os.path.join(self.proj, ".vibecoding", "config.json"), b'{"a": 1}\n')

        ext = self.ext_dir()
        with open(os.path.join(ext, "config.json"), "wb") as fh:
            fh.write(b"USER DATA\n")
        shutil.rmtree(os.path.join(self.proj, ".vibecoding"))
        self.assertTrue(junction(os.path.join(self.proj, ".vibecoding"), ext))
        self.addCleanup(rmdir_link, os.path.join(self.proj, ".vibecoding"))

        actions = journal.rollback()
        self.assertIn("Skipped(out-of-boundary)", "\n".join(actions))
        with open(os.path.join(ext, "config.json"), "rb") as fh:
            self.assertEqual(fh.read(), b"USER DATA\n",
                             "回滚不得删除或覆盖项目外数据")


class TestMatrix(Base):
    """Owner 要求的矩阵补充：跨盘符、重复接入、幂等、块资产一致性。"""

    def test_cross_drive_records_usable_absolute_path(self):
        if os.path.splitdrive(self.proj)[0].lower() == os.path.splitdrive(SKILL_ROOT)[0].lower():
            self.skipTest("项目与技能同盘，无法构造跨盘符")
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        cfg = json.loads(self.read(".vibecoding/config.json").decode("utf-8"))
        self.assertTrue(os.path.isabs(cfg["standard_vendor_path"]),
                        "跨盘符无法相对化，必须退化为可用的绝对路径")
        self.assertTrue(os.path.isdir(cfg["standard_vendor_path"]))

    def test_repeated_adoption_twice_is_idempotent(self):
        self.assertEqual(self.init("--apply")[0], 0)
        snap = snapshot(self.proj)
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.proj), snap)
        self.assertNotIn("created", out)
        self.assertNotIn("appended", out)

    def test_remove_block_only_does_not_touch_other_content(self):
        """块外内容在两次运行之间被改动：仍只动块内"""
        self.write("AGENTS.md", "# 原\n")
        self.assertEqual(self.init("--apply")[0], 0)
        p = os.path.join(self.proj, "AGENTS.md")
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        with open(p, "wb") as fh:
            fh.write(("# 原\n\n- 用户新增一行\n" + txt[txt.find(vb_init.BEGIN):]).encode("utf-8"))
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        with open(p, encoding="utf-8") as fh:
            now = fh.read()
        self.assertIn("用户新增一行", now, "块外内容不得被动")
        self.assertEqual(now.count("<!-- vibecoding:begin"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
