# -*- coding: utf-8 -*-
"""离线回归：清单、发布包和证据门禁。仅使用 Python 标准库。"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(root: Path, names: list[str]) -> None:
    (root / "MANIFEST.sha256").write_text(
        "".join(f"{digest(root / name)} *{name}\n" for name in sorted(names)), encoding="utf-8"
    )


def run_tool(root: Path, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "tools" / script), *args],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def make_manifest_fixture(copy_verify: bool = True, copy_release: bool = True) -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vibecoding-tools-"))
    (temp / "tools").mkdir()
    (temp / "README.md").write_text("fixture\n", encoding="utf-8")
    if copy_verify:
        shutil.copy2(TOOLS / "verify_manifest.py", temp / "tools" / "verify_manifest.py")
    if copy_release:
        shutil.copy2(TOOLS / "release_zip.py", temp / "tools" / "release_zip.py")
    names = ["README.md"]
    if copy_verify:
        names.append("tools/verify_manifest.py")
    if copy_release:
        names.append("tools/release_zip.py")
    write_manifest(temp, names)
    return temp


class ManifestRegressionTests(unittest.TestCase):
    def test_git_clone_is_not_unregistered(self) -> None:
        temp = make_manifest_fixture()
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / ".git").mkdir()
        (temp / ".git" / "config").write_text("gitdir fixture\n", encoding="utf-8")
        result = run_tool(temp, "verify_manifest.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_hash_change_missing_and_new_file_are_reported(self) -> None:
        temp = make_manifest_fixture()
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "README.md").write_text("changed\n", encoding="utf-8")
        (temp / "new.txt").write_text("new\n", encoding="utf-8")
        result = run_tool(temp, "verify_manifest.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("README.md", result.stdout)
        self.assertIn("new.txt", result.stdout)
        (temp / "README.md").unlink()
        result = run_tool(temp, "verify_manifest.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺失", result.stdout)

    def test_illegal_manifest_path_is_rejected(self) -> None:
        temp = make_manifest_fixture(copy_verify=True, copy_release=True)
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "MANIFEST.sha256").write_text(f"{'0' * 64} *../outside.txt\n", encoding="utf-8")
        result = run_tool(temp, "verify_manifest.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("清单无效", result.stdout)


class ReleaseRegressionTests(unittest.TestCase):
    def test_release_build_verify_and_extra_member(self) -> None:
        temp = make_manifest_fixture(copy_verify=False, copy_release=True)
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / ".git").mkdir()
        archive = temp / "fixture.zip"
        built = run_tool(temp, "release_zip.py", "build", str(archive))
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        verified = run_tool(temp, "release_zip.py", "verify", str(archive))
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        with zipfile.ZipFile(archive, "a") as zf:
            zf.writestr("Vibecoding规范/extra.txt", "unexpected")
        tampered = run_tool(temp, "release_zip.py", "verify", str(archive))
        self.assertEqual(tampered.returncode, 1)
        self.assertIn("多出", tampered.stdout)


def evidence_text(result: str, command: str = "python -V", exit_code: str = "0", evidence: str = "artifact.log", limit: str = "无") -> str:
    return f"""# TASK-001 验证记录

Task: TASK-001
Time: 2026-10-23 12:00 Asia/Shanghai
Baseline: abc123
Environment: Windows / Python {sys.version_info.major}.{sys.version_info.minor}

| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | {command} | {exit_code} | {result} | {evidence} | {limit} |

结论：{result}
"""


class EvidenceGateTests(unittest.TestCase):
    def run_check(self, content: str, *args: str) -> subprocess.CompletedProcess[str]:
        temp = Path(tempfile.mkdtemp(prefix="vibecoding-evidence-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "tools").mkdir()
        shutil.copy2(TOOLS / "check_evidence.py", temp / "tools" / "check_evidence.py")
        (temp / "artifact.log").write_text("executed\n", encoding="utf-8")
        evidence = temp / "evidence.md"
        evidence.write_text(content, encoding="utf-8")
        return run_tool(temp, "check_evidence.py", str(evidence), *args)

    def test_pass_requires_execution_and_existing_evidence(self) -> None:
        result = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--acceptance-id", "AC-001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        missing = self.run_check(evidence_text("PASS", evidence="N/A"), "--task-id", "TASK-001")
        self.assertEqual(missing.returncode, 1)
        no_execution = self.run_check(evidence_text("PASS", command="<命令>"), "--task-id", "TASK-001")
        self.assertEqual(no_execution.returncode, 1)

    def test_blocked_and_missing_acceptance_cannot_be_done(self) -> None:
        blocked = self.run_check(
            evidence_text("BLOCKED", command="N/A", exit_code="N/A", evidence="N/A", limit="服务不可用"),
            "--task-status", "DONE", "--acceptance-id", "AC-001",
        )
        self.assertEqual(blocked.returncode, 1)
        missing = self.run_check(evidence_text("PASS"), "--acceptance-id", "AC-002")
        self.assertEqual(missing.returncode, 1)

    def test_overall_pass_contradiction_is_rejected(self) -> None:
        content = evidence_text("NOT_RUN", command="N/A", exit_code="N/A", evidence="N/A", limit="依赖未就绪").replace("结论：NOT_RUN", "结论：PASS")
        result = self.run_check(content)
        self.assertEqual(result.returncode, 1)
        self.assertIn("矛盾", result.stdout)

    def test_time_and_timezone_are_required(self) -> None:
        for valid_time in (
            "2026-10-23 12:00 Asia/Shanghai",
            "2026-10-23T12:00:00+08:00",
            "2026-10-23 04:00 UTC",
            "2024-02-29 12:00 UTC",
        ):
            valid = self.run_check(
                evidence_text("PASS").replace("Time: 2026-10-23 12:00 Asia/Shanghai", f"Time: {valid_time}"),
                "--task-id", "TASK-001",
            )
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        for invalid_time in (
            "",
            "<日期、时间、时区>",
            "UTC",
            "2026-10-23 UTC",
            "12:00 UTC",
            "2026-10-23 12:00",
            "2026-99-99 25:61 UTC",
            "2026-13-01 12:00 UTC",
            "2026-02-30 12:00 UTC",
            "2025-02-29 12:00 UTC",
            "2026-10-23 24:00 UTC",
            "2026-10-23 12:61 UTC",
            "2026-10-23 12:00 +25:00",
        ):
            content = evidence_text("PASS").replace("Time: 2026-10-23 12:00 Asia/Shanghai", f"Time: {invalid_time}")
            result = self.run_check(content, "--task-id", "TASK-001")
            self.assertNotEqual(result.returncode, 0, invalid_time)
            self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
        for invalid_time, marker in (
            ("2026-99-99 25:61 UTC", "日期取值非法"),
            ("2026-10-23 24:00 UTC", "具体时刻取值非法"),
            ("2026-10-23 12:00 +25:00", "UTC 偏移量非法"),
        ):
            result = self.run_check(
                evidence_text("PASS").replace("Time: 2026-10-23 12:00 Asia/Shanghai", f"Time: {invalid_time}"),
                "--task-id", "TASK-001",
            )
            self.assertNotEqual(result.returncode, 0, invalid_time)
            self.assertIn(marker, result.stdout)

    def test_pass_command_must_be_real_and_manual_na_is_explicit(self) -> None:
        for command in ("N/A", "无", ""):
            content = evidence_text("PASS", command=command)
            result = self.run_check(content, "--task-id", "TASK-001")
            self.assertNotEqual(result.returncode, 0, command)
        manual = evidence_text(
            "PASS", command="人工检查：核对页面状态", exit_code="N/A", limit="由审查者核对并记录"
        )
        result = self.run_check(manual, "--task-id", "TASK-001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        automated_failure = evidence_text("PASS", command="python -V", exit_code="1")
        result = self.run_check(automated_failure, "--task-id", "TASK-001")
        self.assertEqual(result.returncode, 1)

    def test_done_distinguishes_optional_na_from_required_acceptance(self) -> None:
        optional_na = evidence_text("PASS")
        optional_na = optional_na.replace(
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |",
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |\n| AC-OPTIONAL | N/A | N/A | N/A | N/A | 与本任务无关：不适用 |",
        )
        result = self.run_check(optional_na, "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        ignored_row_guard = optional_na.replace("与本任务无关：不适用", "N/A")
        result = self.run_check(ignored_row_guard, "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001")
        self.assertEqual(result.returncode, 1)
        self.assertIn("AC-OPTIONAL", result.stdout)

        required_na = evidence_text("N/A", command="N/A", exit_code="N/A", evidence="N/A", limit="明确不适用")
        result = self.run_check(required_na, "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001")
        self.assertEqual(result.returncode, 1)
        no_reason_na = evidence_text("N/A", command="N/A", exit_code="N/A", evidence="N/A", limit="N/A")
        result = self.run_check(no_reason_na, "--task-id", "TASK-001")
        self.assertNotEqual(result.returncode, 0)

        no_authoritative_range = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "DONE")
        self.assertEqual(no_authoritative_range.returncode, 2)
        self.assertNotIn("== 证据门禁: PASS ==", no_authoritative_range.stdout)

    def test_not_run_and_blocked_require_real_reasons(self) -> None:
        for result_name in ("NOT_RUN", "BLOCKED"):
            valid = self.run_check(evidence_text(result_name, command="N/A", exit_code="N/A", evidence="N/A", limit="依赖服务不可用"))
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            for reason in ("N/A", "无", ""):
                invalid = self.run_check(evidence_text(result_name, command="N/A", exit_code="N/A", evidence="N/A", limit=reason))
                self.assertNotEqual(invalid.returncode, 0, (result_name, reason))

    def test_external_evidence_and_following_tables_are_not_false_failures(self) -> None:
        external = evidence_text("PASS", evidence="https://example.invalid/artifact.log")
        result = self.run_check(external, "--task-id", "TASK-001", "--require-path", "https://example.invalid/index")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

        unrelated = evidence_text("PASS") + "\n\n## 其他说明\n\n| 字段 | 值 |\n| --- | --- |\n| note | ignored |\n"
        result = self.run_check(unrelated, "--task-id", "TASK-001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gate_is_read_only(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="vibecoding-evidence-readonly-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "tools").mkdir()
        shutil.copy2(TOOLS / "check_evidence.py", temp / "tools" / "check_evidence.py")
        (temp / "artifact.log").write_text("executed\n", encoding="utf-8")
        evidence = temp / "evidence.md"
        evidence.write_text(evidence_text("PASS"), encoding="utf-8")
        before = evidence.read_bytes()
        result = run_tool(temp, "check_evidence.py", str(evidence), "--task-id", "TASK-001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(evidence.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
