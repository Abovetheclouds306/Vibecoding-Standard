# -*- coding: utf-8 -*-
"""vb_init.py 的 P1-CLI 测试：--json 失败契约、--update-block 退出码、注入块防漂移、
vendor 定位与项目搬迁、技能缺失时如实报告、重复执行幂等。

全部在系统临时目录进行。设置 VB_INIT_UNDER_TEST 可对其他版本（如 c08407d）跑同一批用例以证明判别力。
"""
from __future__ import annotations

import contextlib
import hashlib
import subprocess
from unittest import mock
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.abspath(os.path.join(HERE, "..", "vibecoding"))
SCRIPT = os.environ.get("VB_INIT_UNDER_TEST") or os.path.join(SKILL_ROOT, "scripts", "vb_init.py")
ASSET = os.path.join(SKILL_ROOT, "assets", "AGENTS.block.md")
# 显式传 --standard：被测脚本可能是复制到临时目录的旧版本，不能依赖它相对自身位置找 vendor
VENDOR = os.path.join(SKILL_ROOT, "vendor", "vibecoding-standard")

_spec = importlib.util.spec_from_file_location("vb_init_cli_under_test", SCRIPT)
vb_init = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vb_init)


def snapshot(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d != ".git"]
        for f in fns:
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = hashlib.sha256(fh.read()).hexdigest()
    return out


def run_main(argv):
    buf = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        try:
            rc = vb_init.main(argv)
        except SystemExit as exc:
            rc = exc.code
    return rc, buf.getvalue()


def norm(b: bytes) -> str:
    return b.decode("utf-8").replace("\r\n", "\n").strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vbcli-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(self.proj)

    def install_skill_into_project(self, proj=None):
        """模拟项目内安装：复制技能到 <proj>/.claude/skills/vibecoding（临时目录内）。"""
        dst = os.path.join(proj or self.proj, ".claude", "skills", "vibecoding")
        shutil.copytree(SKILL_ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return os.path.join(dst, "vendor", "vibecoding-standard")

    def init(self, *extra, proj=None):
        if "--standard" not in extra and "--no-such-flag" not in extra:
            extra = (*extra, "--standard", VENDOR)
        return run_main(["--project", proj or self.proj, *extra])

    def assert_json_contract(self, rc, out):
        try:
            data = json.loads(out)
        except ValueError:
            self.fail("--json 输出必须是单个 JSON 对象，实际为:\n%s" % out[:400])
        self.assertIsInstance(data, dict)
        for k in ("status", "rc", "steps", "needs_decision", "block_updated"):
            self.assertIn(k, data, "JSON 缺少契约字段 %s" % k)
        self.assertEqual(data["rc"], rc, "JSON rc 必须等于进程退出码")
        return data


class TestJsonFailureContract(Base):
    def test_missing_project_dir(self):
        rc, out = run_main(["--project", os.path.join(self.tmp, "nope"), "--json"])
        self.assertEqual(rc, 1)
        data = self.assert_json_contract(rc, out)
        self.assertIn(data["status"], ("refused", "failed"))
        self.assertTrue(data["error"])

    def test_missing_standard(self):
        rc, out = self.init("--apply", "--json", "--standard", os.path.join(self.tmp, "no-vendor"))
        self.assertEqual(rc, 1)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "refused")
        self.assertEqual(snapshot(self.proj), {}, "拒绝时不得写入任何文件")

    def test_broken_vendor(self):
        bad = os.path.join(self.tmp, "bad-vendor")
        os.makedirs(bad)
        rc, out = self.init("--apply", "--json", "--standard", bad)
        self.assertEqual(rc, 1)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "refused")

    def test_usage_error(self):
        rc, out = self.init("--json", "--no-such-flag")
        self.assertEqual(rc, 2)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "usage_error")

    def test_success_has_status_ok(self):
        rc, out = self.init("--apply", "--json")
        self.assertEqual(rc, 0, out)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "ok")


class TestUpdateBlockExitCode(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.init("--apply")[0], 0)
        p = os.path.join(self.proj, "AGENTS.md")
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(txt.replace("**证据**", "**证据（人工）**", 1))

    def test_differs_json_needs_decision_rc2(self):
        rc, out = self.init("--apply", "--json")
        self.assertEqual(rc, 2)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "needs_decision")
        self.assertTrue(data["needs_decision"])

    def test_update_block_json_rc0_and_state_consistent(self):
        rc, out = self.init("--apply", "--update-block", "--json")
        self.assertEqual(rc, 0)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["block_updated"])
        with open(os.path.join(self.proj, "AGENTS.md"), encoding="utf-8") as fh:
            self.assertNotIn("证据（人工）", fh.read())
        rc2, out2 = self.init("--apply", "--json")
        self.assertEqual(rc2, 0, "更新后再跑应无待决事项")


class TestBlockDrift(Base):
    def test_injected_block_equals_asset_for_project_install(self):
        vendor = self.install_skill_into_project()
        rc, out = self.init("--apply", "--standard", vendor)
        self.assertEqual(rc, 0, out)
        with open(ASSET, "rb") as fh:
            asset = norm(fh.read())
        with open(os.path.join(self.proj, "AGENTS.md"), "rb") as fh:
            agents = norm(fh.read())
        i = agents.find(vb_init.BEGIN)
        j = agents.find(vb_init.END, i)
        self.assertGreaterEqual(i, 0)
        self.assertEqual(agents[i:j + len(vb_init.END)], asset,
                         "assets/AGENTS.block.md 与 vb_init.BLOCK 渲染结果已漂移")


class TestVendorMoveAndMissing(Base):
    def test_project_move_keeps_relative_vendor_and_rerun_idempotent(self):
        vendor = self.install_skill_into_project()
        self.assertEqual(self.init("--apply", "--standard", vendor)[0], 0)
        moved = os.path.join(self.tmp, "moved-proj")
        shutil.move(self.proj, moved)
        with open(os.path.join(moved, ".vibecoding", "config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        vp = cfg["standard_vendor_path"]
        self.assertFalse(os.path.isabs(vp), "项目内 vendor 必须记录为相对路径")
        self.assertTrue(os.path.isfile(os.path.join(moved, vp, "AI_PROJECT_STANDARD.md")))
        before = snapshot(moved)
        new_vendor = os.path.join(moved, ".claude", "skills", "vibecoding", "vendor", "vibecoding-standard")
        rc, out = self.init("--apply", "--standard", new_vendor, proj=moved)
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(moved), before, "搬迁后重跑应幂等")

    def test_skill_removed_reports_honestly(self):
        vendor = self.install_skill_into_project()
        self.assertEqual(self.init("--apply", "--standard", vendor)[0], 0)
        shutil.rmtree(os.path.join(self.proj, ".claude"))
        before = snapshot(self.proj)
        rc, out = self.init("--apply", "--json", "--standard", vendor)
        self.assertEqual(rc, 1)
        data = self.assert_json_contract(rc, out)
        self.assertEqual(data["status"], "refused")
        self.assertEqual(snapshot(self.proj), before, "技能缺失时不得改写项目文件")

    def test_init_rerun_idempotent(self):
        self.assertEqual(self.init("--apply")[0], 0)
        before = snapshot(self.proj)
        rc, out = self.init("--apply")
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.proj), before)


class TestR4N2CompensateOwnership(Base):
    """R4-N2：写入失败后的就地补偿必须有归属判据，且识别本次新建目录被替换为 Junction。"""

    def test_other_process_content_not_deleted_and_not_claimed_rolled_back(self):
        target = os.path.join(self.proj, ".vibecoding", "HANDOFF.md")
        real_replace = vb_init._replace

        def rep(src, dst):
            if os.path.basename(dst) == "HANDOFF.md":
                with open(dst, "wb") as fh:
                    fh.write(b"OTHER PROCESS DATA\n")
                raise PermissionError(13, "injected: target busy")
            return real_replace(src, dst)

        with mock.patch.object(vb_init, "_replace", rep):
            rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        self.assertTrue(os.path.isfile(target), "不得删除不是本进程写入的内容")
        with open(target, "rb") as fh:
            self.assertEqual(fh.read(), b"OTHER PROCESS DATA\n")
        self.assertIn("ResidualRisk", out)
        self.assertNotIn("FAILED（已回滚", out)

    def test_created_dir_swapped_to_in_project_junction_not_followed(self):
        if os.name != "nt":
            self.skipTest("NOT_RUN: Junction 仅 Windows")
        decoy = os.path.join(self.proj, "decoy")
        os.makedirs(decoy)
        with open(os.path.join(decoy, "config.json"), "wb") as fh:
            fh.write(b"USER CONFIG IN DECOY\n")
        vb = os.path.join(self.proj, ".vibecoding")
        real_replace = vb_init._replace
        fired = []

        def rep(src, dst):
            if os.path.basename(dst) == "config.json" and not fired:
                os.remove(src)
                os.rename(vb, vb + "_moved")
                ok = subprocess.run(["cmd", "/c", "mklink", "/J", vb, decoy], capture_output=True).returncode == 0
                fired.append(ok)
                raise OSError(5, "injected commit failure")
            return real_replace(src, dst)

        try:
            with mock.patch.object(vb_init, "_replace", rep):
                rc, out = self.init("--apply")
        finally:
            if os.path.lexists(vb):
                subprocess.run(["cmd", "/c", "rmdir", vb], capture_output=True)
        if not fired or not fired[0]:
            self.skipTest("NOT_RUN: 无法创建 Junction")
        self.assertEqual(rc, 1, out)
        with open(os.path.join(decoy, "config.json"), "rb") as fh:
            self.assertEqual(fh.read(), b"USER CONFIG IN DECOY\n", "不得经项目内 Junction 删除用户文件")
        self.assertIn("ResidualRisk", out)
        self.assertNotIn("FAILED（已回滚", out)


class TestR5N2RealLocationAndRollbackResiduals(Base):
    """R5-N2：保护 R4-N2 的核心机制。回滚前把目录换成指向项目内、内容逐字节相同副本的 Junction，
    只比对内容无法识别，必须靠“新建目录登记真实位置 + 父路径真实位置比对”；并保护回滚跳过项进残留。"""

    def _fail_handoff_after_commit(self):
        real = vb_init._replace

        def rep(src, dst):
            r = real(src, dst)
            if os.path.basename(dst) == "HANDOFF.md":
                raise PermissionError(13, "injected after commit")
            return r
        return rep

    def _swap_at_rollback(self, rel, *extra):
        if os.name != "nt":
            self.skipTest("NOT_RUN: Junction 仅 Windows")
        d = os.path.join(self.proj, *rel.split("/"))
        decoy = os.path.join(self.proj, "decoy_" + rel.replace("/", "_").strip("."))
        real_rb = vb_init.WriteJournal.rollback
        st = {}

        def rb(journal):
            shutil.copytree(d, decoy)
            os.rename(d, d + "_moved")
            st["j"] = subprocess.run(["cmd", "/c", "mklink", "/J", d, decoy], capture_output=True).returncode == 0
            st["before"] = snapshot(decoy)
            return real_rb(journal)

        try:
            with mock.patch.object(vb_init, "_replace", self._fail_handoff_after_commit()), \
                    mock.patch.object(vb_init.WriteJournal, "rollback", rb):
                rc, out = self.init("--apply", *extra)
        finally:
            if os.path.lexists(d) and os.path.realpath(d) != os.path.abspath(d):
                subprocess.run(["cmd", "/c", "rmdir", d], capture_output=True)
        if not st.get("j"):
            self.skipTest("NOT_RUN: 无法创建 Junction")
        self.assertTrue(st["before"], "副本应非空（逐字节相同的已写入文件）")
        self.assertEqual(rc, 1, out)
        self.assertEqual(snapshot(decoy), st["before"], "不得经项目内 Junction 改动/删除副本中的文件")
        return out

    def _assert_honest(self, out):
        self.assertIn("ResidualRisk", out)
        self.assertNotIn("FAILED（已回滚", out)

    def test_E1_created_dir_swapped_to_identical_in_project_copy(self):
        self._assert_honest(self._swap_at_rollback(".vibecoding"))

    def test_E3_nested_created_dir_swapped_to_identical_in_project_copy(self):
        self._assert_honest(self._swap_at_rollback(".vibecoding/evidence"))

    def test_E2_preexisting_dir_swapped_to_identical_in_project_copy(self):
        os.makedirs(os.path.join(self.proj, ".vibecoding"))
        with open(os.path.join(self.proj, ".vibecoding", "user_note.txt"), "wb") as fh:
            fh.write(b"USER NOTE\n")
        self._assert_honest(self._swap_at_rollback(".vibecoding"))
        with open(os.path.join(self.proj, ".vibecoding_moved", "user_note.txt"), "rb") as fh:
            self.assertEqual(fh.read(), b"USER NOTE\n")

    def test_E7_json_reports_failed_with_residuals_no_rollback_claim(self):
        out = self._swap_at_rollback(".vibecoding", "--json")
        j = json.loads(out)
        self.assertEqual((j.get("status"), j.get("rc")), ("failed", 1), out)
        self._assert_honest(json.dumps(j, ensure_ascii=False))

    def test_modified_by_others_at_rollback_is_residual(self):
        hf = os.path.join(self.proj, ".vibecoding", "HANDOFF.md")
        real_rb = vb_init.WriteJournal.rollback

        def rb(journal):
            with open(hf, "wb") as fh:
                fh.write(b"OTHER PROCESS AFTER COMPENSATION\n")
            return real_rb(journal)

        with mock.patch.object(vb_init, "_replace", self._fail_handoff_after_commit()), \
                mock.patch.object(vb_init.WriteJournal, "rollback", rb):
            rc, out = self.init("--apply")
        self.assertEqual(rc, 1, out)
        with open(hf, "rb") as fh:
            self.assertEqual(fh.read(), b"OTHER PROCESS AFTER COMPENSATION\n")
        self._assert_honest(out)



class R7Helper(Base):
    def mk_junction(self, link, target):
        if os.name != "nt":
            return False
        ok = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True).returncode == 0
        if ok:
            self.addCleanup(lambda: os.path.lexists(link) and subprocess.run(["cmd", "/c", "rmdir", link],
                                                                               capture_output=True))
        return ok

    def residual_lines(self, out, name):
        return [l for l in out.splitlines() if "ResidualRisk" in l and name in l]

class TestR4N9DriveRoot(R7Helper):
    def test_R4N9_drive_root_inside_and_guard(self):
        root = os.path.abspath(os.sep)
        self.assertTrue(vb_init._inside(os.path.join(root, "AGENTS.md"), root))
        vb_init.WriteJournal(root=root).guard(os.path.join(root, "AGENTS.md"))  # 只校验、不写盘


if __name__ == "__main__":
    unittest.main(verbosity=2)
