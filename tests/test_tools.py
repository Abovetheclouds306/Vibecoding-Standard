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
        result = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "REVIEW", "--acceptance-id", "AC-001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        missing = self.run_check(evidence_text("PASS", evidence="N/A"), "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(missing.returncode, 1)
        no_execution = self.run_check(evidence_text("PASS", command="<命令>"), "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(no_execution.returncode, 1)

    def test_blocked_and_missing_acceptance_cannot_be_done(self) -> None:
        blocked = self.run_check(
            evidence_text("BLOCKED", command="N/A", exit_code="N/A", evidence="N/A", limit="服务不可用"),
            "--task-status", "DONE", "--acceptance-id", "AC-001",
        )
        self.assertEqual(blocked.returncode, 1)
        missing = self.run_check(evidence_text("PASS"), "--task-status", "REVIEW", "--acceptance-id", "AC-002")
        self.assertEqual(missing.returncode, 1)

    def test_overall_pass_contradiction_is_rejected(self) -> None:
        content = evidence_text("NOT_RUN", command="N/A", exit_code="N/A", evidence="N/A", limit="依赖未就绪").replace("结论：NOT_RUN", "结论：PASS")
        result = self.run_check(content, "--task-status", "REVIEW")
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
                "--task-id", "TASK-001", "--task-status", "REVIEW",
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
            result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertNotEqual(result.returncode, 0, invalid_time)
            self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
        for invalid_time, marker in (
            ("2026-99-99 25:61 UTC", "日期取值非法"),
            ("2026-10-23 24:00 UTC", "具体时刻取值非法"),
            ("2026-10-23 12:00 +25:00", "UTC 偏移量非法"),
        ):
            result = self.run_check(
                evidence_text("PASS").replace("Time: 2026-10-23 12:00 Asia/Shanghai", f"Time: {invalid_time}"),
                "--task-id", "TASK-001", "--task-status", "REVIEW",
            )
            self.assertNotEqual(result.returncode, 0, invalid_time)
            self.assertIn(marker, result.stdout)

    def test_pass_command_must_be_real_and_manual_na_is_explicit(self) -> None:
        for command in ("N/A", "无", ""):
            content = evidence_text("PASS", command=command)
            result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertNotEqual(result.returncode, 0, command)
        manual = evidence_text(
            "PASS", command="人工检查：核对页面状态", exit_code="N/A", limit="由审查者核对并记录"
        )
        result = self.run_check(manual, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        automated_failure = evidence_text("PASS", command="python -V", exit_code="1")
        result = self.run_check(automated_failure, "--task-id", "TASK-001", "--task-status", "REVIEW")
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
        result = self.run_check(no_reason_na, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertNotEqual(result.returncode, 0)

        no_authoritative_range = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "DONE")
        self.assertEqual(no_authoritative_range.returncode, 2)
        self.assertNotIn("== 证据门禁: PASS ==", no_authoritative_range.stdout)

    def test_not_run_and_blocked_require_real_reasons(self) -> None:
        # 契约 4：非 DONE 状态下，原因有效的 NOT_RUN/BLOCKED 不是失败，但绝不能呈现为 PASS。
        for result_name in ("NOT_RUN", "BLOCKED"):
            valid = self.run_check(
                evidence_text(result_name, command="N/A", exit_code="N/A", evidence="N/A", limit="依赖服务不可用"),
                "--task-status", "REVIEW",
            )
            self.assertEqual(valid.returncode, 2, valid.stdout + valid.stderr)
            self.assertIn("== 证据门禁: UNKNOWN ==", valid.stdout)
            self.assertNotIn("== 证据门禁: PASS ==", valid.stdout)
            self.assertIn("验证未完成", valid.stdout)
            for reason in ("N/A", "无", ""):
                invalid = self.run_check(
                    evidence_text(result_name, command="N/A", exit_code="N/A", evidence="N/A", limit=reason),
                    "--task-status", "REVIEW",
                )
                self.assertEqual(invalid.returncode, 1, (result_name, reason, invalid.stdout))
            # 契约 5：DONE 状态下未执行的必要验收是确定失败，不是 UNKNOWN。
            done = self.run_check(
                evidence_text(result_name, command="N/A", exit_code="N/A", evidence="N/A", limit="依赖服务不可用"),
                "--task-status", "DONE", "--acceptance-id", "AC-001",
            )
            self.assertEqual(done.returncode, 1, (result_name, done.stdout))
            self.assertIn("== 证据门禁: FAIL ==", done.stdout)
        # 反向：合法完成（全 PASS）的 REVIEW/IN_PROGRESS 证据不得因本判定被误判为失败。
        for status in ("REVIEW", "IN_PROGRESS", "BLOCKED"):
            legal = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", status)
            self.assertEqual(legal.returncode, 0, (status, legal.stdout + legal.stderr))
            self.assertIn("== 证据门禁: PASS ==", legal.stdout)

    def test_external_evidence_and_following_tables_are_not_false_failures(self) -> None:
        external = evidence_text("PASS", evidence="https://example.invalid/artifact.log")
        result = self.run_check(
            external, "--task-id", "TASK-001", "--task-status", "REVIEW", "--require-path", "https://example.invalid/index"
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

        unrelated = evidence_text("PASS") + "\n\n## 其他说明\n\n| 字段 | 值 |\n| --- | --- |\n| note | ignored |\n"
        result = self.run_check(unrelated, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_second_acceptance_table_is_not_silently_ignored(self) -> None:
        # 首个表全 PASS、第二个验收表全 FAIL：不得因只解析首表而输出 PASS。
        content = evidence_text("PASS").replace("结论：PASS", "") + (
            "\n补充记录：\n\n"
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-002 | pytest -q tests/e2e | 1 | FAIL | artifact.log | 全部失败 |\n"
        )
        result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("额外验收表", result.stdout)
        # 诊断须可定位：给出额外表所在行号，且明确不支持跨表聚合验证。
        self.assertIn("行号", result.stdout)
        self.assertIn("不支持跨表聚合验证", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

        # D-02：已可靠解析出的明确 FAIL 优先于 UNKNOWN，不得因存在额外表而降级为 2。
        fail_with_extra = (
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-001 | pytest -q | 1 | FAIL | artifact.log | 失败 |\n"
            "\n补充记录：\n\n"
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-002 | pytest -q | 0 | PASS | artifact.log | 无 |\n"
        )
        head = evidence_text("PASS").split("| 验收 ID")[0]
        result = self.run_check(head + fail_with_extra, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)
        self.assertNotIn("== 证据门禁: UNKNOWN ==", result.stdout)

        # 第二个表把「命令」列改名为「步骤」，仍须被检出，不能因列名不同而漏判。
        renamed = evidence_text("PASS").replace("结论：PASS", "") + (
            "\n补充记录：\n\n"
            "| 验收 ID | 步骤 | 退出码 | 结论 | 证据 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-002 | pytest -q tests/e2e | 1 | FAIL | artifact.log | 全部失败 |\n"
        )
        result = self.run_check(renamed, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("额外验收表", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

    def test_gate_is_read_only(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="vibecoding-evidence-readonly-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "tools").mkdir()
        shutil.copy2(TOOLS / "check_evidence.py", temp / "tools" / "check_evidence.py")
        (temp / "artifact.log").write_text("executed\n", encoding="utf-8")
        evidence = temp / "evidence.md"
        evidence.write_text(evidence_text("PASS"), encoding="utf-8")
        before = evidence.read_bytes()
        result = run_tool(temp, "check_evidence.py", str(evidence), "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(evidence.read_bytes(), before)

    def test_fail_rows_and_summary_fail_never_pass(self) -> None:
        two_fail = evidence_text("FAIL", command="python -V", exit_code="1", limit="命令失败")
        two_fail = two_fail.replace(
            "| AC-001 | python -V | 1 | FAIL | artifact.log | 命令失败 |",
            "| AC-001 | python -V | 1 | FAIL | artifact.log | 命令失败 |\n| AC-002 | python -V | 1 | FAIL | artifact.log | 命令失败 |",
        ).replace("结论：FAIL", "")
        result = self.run_check(two_fail, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)
        self.assertIn("AC-001 验收结论为 FAIL", result.stdout)
        self.assertIn("AC-002 验收结论为 FAIL", result.stdout)

        summary_fail = evidence_text("PASS").replace("结论：PASS", "结论：FAIL")
        result = self.run_check(summary_fail, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1)
        self.assertIn("总结论明确为 FAIL", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

        # 反向：不得因引入 FAIL 判定而把正常记录误判为失败。
        clean = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn("== 证据门禁: PASS ==", clean.stdout)

    def test_fail_dominates_unknown_when_status_omitted(self) -> None:
        # 省略状态产生 UNKNOWN，但已确定的 FAIL 必须优先，不得降级为 2。
        content = evidence_text("FAIL", command="python -V", exit_code="1", limit="命令失败")
        result = self.run_check(content, "--task-id", "TASK-001")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)
        self.assertNotIn("== 证据门禁: UNKNOWN ==", result.stdout)

    def test_omitted_status_is_unknown_but_review_can_pass(self) -> None:
        content = evidence_text("PASS")
        omitted = self.run_check(content, "--task-id", "TASK-001")
        self.assertEqual(omitted.returncode, 2)
        self.assertIn("未提供任务状态", omitted.stdout)
        self.assertIn("未执行 DONE 完整性检查", omitted.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", omitted.stdout)

        review = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)

    def test_non_done_status_declares_skipped_completion_check(self) -> None:
        for status in ("REVIEW", "IN_PROGRESS", "BLOCKED"):
            result = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", status)
            self.assertEqual(result.returncode, 0, f"{status}: {result.stdout}{result.stderr}")
            self.assertIn("未执行 DONE 完整性检查", result.stdout, status)
            self.assertNotIn("DONE 完整性检查通过", result.stdout, status)

    def test_done_requires_authoritative_acceptance_set(self) -> None:
        missing_id = self.run_check(
            evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-002"
        )
        # 必要验收集合已给出且可读，记录中确实缺失 —— 这是确定事实，属 FAIL 而非 UNKNOWN。
        self.assertEqual(missing_id.returncode, 1, missing_id.stdout)
        self.assertIn("缺少必要验收记录: AC-002", missing_id.stdout)
        self.assertIn("== 证据门禁: FAIL ==", missing_id.stdout)

        failed_required = self.run_check(
            evidence_text("FAIL", command="python -V", exit_code="1", limit="命令失败"),
            "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001",
        )
        self.assertEqual(failed_required.returncode, 1)

        complete = self.run_check(
            evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001"
        )
        self.assertEqual(complete.returncode, 0, complete.stdout + complete.stderr)
        self.assertIn("DONE 完整性检查通过", complete.stdout)

    def test_unreadable_evidence_is_fail_with_line_prefix(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="vibecoding-evidence-unreadable-"))
        self.addCleanup(shutil.rmtree, temp, ignore_errors=True)
        (temp / "tools").mkdir()
        shutil.copy2(TOOLS / "check_evidence.py", temp / "tools" / "check_evidence.py")

        missing_file = run_tool(temp, "check_evidence.py", str(temp / "absent.md"), "--task-status", "REVIEW")
        self.assertEqual(missing_file.returncode, 1)
        self.assertIn("FAIL: 无法读取证据文件", missing_file.stdout)
        self.assertIn("== 证据门禁: FAIL ==", missing_file.stdout)

        undecodable = temp / "undecodable.md"
        undecodable.write_bytes(b"# \xff\xfe\x00 bad utf-8\n")
        broken = run_tool(temp, "check_evidence.py", str(undecodable), "--task-status", "REVIEW")
        # 解码失败必须给出明确 FAIL 结论行，不能只剩裸 traceback。
        self.assertEqual(broken.returncode, 1, broken.stdout + broken.stderr)
        self.assertIn("FAIL: 无法读取证据文件", broken.stdout)
        self.assertIn("== 证据门禁: FAIL ==", broken.stdout)
        self.assertNotIn("Traceback", broken.stderr)

    def test_invalid_task_status_value_is_rejected(self) -> None:
        result = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "FINISHED")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

        lowercase = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "review")
        self.assertEqual(lowercase.returncode, 0, lowercase.stdout + lowercase.stderr)

    def test_empty_evidence_file_is_not_pass(self) -> None:
        result = self.run_check("", "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001")
        self.assertEqual(result.returncode, 1)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

    def test_unfinished_overall_conclusion_is_never_pass(self) -> None:
        # 总结论自述未完成：非 DONE 不得呈现为 PASS；DONE 与「未完成」直接矛盾 → FAIL。
        for overall in ("NOT_RUN", "BLOCKED"):
            content = evidence_text("PASS").replace("结论：PASS", f"结论：{overall}")
            result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertEqual(result.returncode, 2, (overall, result.stdout))
            self.assertIn(f"总结论为 {overall}", result.stdout)
            self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
            done = self.run_check(
                content, "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001"
            )
            self.assertEqual(done.returncode, 1, (overall, done.stdout))
            self.assertIn("== 证据门禁: FAIL ==", done.stdout)
        # 反向：总结论 PASS 且验收行全 PASS 的记录仍必须通过。
        clean = self.run_check(evidence_text("PASS"), "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn("== 证据门禁: PASS ==", clean.stdout)

    def test_optional_na_allows_but_required_na_never_passes(self) -> None:
        content = evidence_text("PASS").replace(
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |",
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |\n"
            "| AC-NA | N/A | N/A | N/A | N/A | 与本任务无关：不适用 |",
        )
        # 契约 8 前段：有理由的非必要 N/A 保留允许行为，IN_PROGRESS/REVIEW/DONE 均不得误判。
        for args in (
            ("--task-status", "REVIEW"),
            ("--task-status", "IN_PROGRESS"),
            ("--task-status", "DONE", "--acceptance-id", "AC-001"),
        ):
            optional = self.run_check(content, "--task-id", "TASK-001", *args)
            self.assertEqual(optional.returncode, 0, (args, optional.stdout + optional.stderr))
            self.assertIn("== 证据门禁: PASS ==", optional.stdout)
        # 契约 8 后段：被登记为必要验收的 N/A 不能视为通过，与任务状态无关。
        for status in ("REVIEW", "IN_PROGRESS"):
            required = self.run_check(
                content, "--task-id", "TASK-001", "--task-status", status, "--acceptance-id", "AC-NA"
            )
            self.assertEqual(required.returncode, 1, (status, required.stdout))
            self.assertIn("必要验收 AC-NA 为 N/A", required.stdout)
            self.assertNotIn("== 证据门禁: PASS ==", required.stdout)

    def test_alias_id_column_acceptance_table_is_detected(self) -> None:
        head = evidence_text("PASS").split("| 验收 ID")[0]
        table = (
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |\n"
        )
        second = (
            "| {id_column} | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-002 | pytest -q tests/e2e | 1 | FAIL | artifact.log | 全部失败 |\n"
        )
        # 首表全 PASS + 第二表全 FAIL：ID 列改名也必须检出，且不得返回 PASS。
        for id_column in ("验收 ID", "验收编号", "用例 ID", "Acceptance"):
            content = head + table + "\n补充记录：\n\n" + second.format(id_column=id_column)
            result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertEqual(result.returncode, 2, (id_column, result.stdout))
            self.assertIn("额外验收表", result.stdout)
            self.assertIn("行号", result.stdout)
            self.assertIn("不支持跨表聚合验证", result.stdout)
            self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
        # 首表已有确定 FAIL 时必须为 FAIL(1)，不得因检出额外表而降级为 2。
        fail_first = head + table.replace(
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |",
            "| AC-001 | pytest -q | 1 | FAIL | artifact.log | 失败 |",
        ) + "\n补充记录：\n\n" + second.format(id_column="用例 ID")
        result = self.run_check(fail_first, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)
        self.assertNotIn("== 证据门禁: UNKNOWN ==", result.stdout)
        # 反向：列名含 ID 但非验收 ID 别名的普通表格不得误报为额外验收表。
        unrelated = evidence_text("PASS") + "\n## 统计\n\n| 项目 ID | 结论 |\n| --- | --- |\n| X-1 | 完成 |\n"
        result = self.run_check(unrelated, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("额外验收表", result.stdout)

    def test_adjacent_acceptance_tables_are_split(self) -> None:
        head = evidence_text("PASS").split("| 验收 ID")[0]
        adjacent = head + (
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |\n"
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-002 | pytest -q tests/e2e | 1 | FAIL | artifact.log | 全部失败 |\n"
        )
        result = self.run_check(adjacent, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("额外验收表", result.stdout)
        self.assertIn("行号：11", result.stdout)
        # 第二表表头不得被当作验收数据行，否则会出现虚假的「验收 ID 无效」诊断。
        self.assertNotIn("验收 ID 无效", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
        # 首表存在确定 FAIL 时仍必须是 FAIL(1)。
        fail_first = adjacent.replace(
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |",
            "| AC-001 | pytest -q | 1 | FAIL | artifact.log | 失败 |",
        )
        result = self.run_check(fail_first, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)
        # 反向：与首表相邻的无关表格不得被误报为「额外验收表」。
        unrelated = head + (
            "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |\n"
            "| 字段 | 值 |\n"
            "| --- | --- |\n"
            "| note | ignored |\n"
        )
        result = self.run_check(unrelated, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertNotIn("额外验收表", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)


    # ---- 假 PASS 回归与表格识别边界 ----
    _MAIN_TABLE = (
        "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |\n"
    )
    _SECOND_HEADER = "| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |\n"
    _SECOND_FAIL_ROW = "| AC-002 | pytest -q tests/e2e | 1 | FAIL | artifact.log | 全部失败 |\n"

    def _head(self) -> str:
        return evidence_text("PASS").split("| 验收 ID")[0]

    def test_incomplete_extra_acceptance_table_never_passes(self) -> None:
        # 第二张验收表漏写 Markdown 分隔行时，旧实现把表头当数据吞掉 → 假 PASS(0)。
        content = (
            self._head() + self._MAIN_TABLE + "\n## 补充验收\n\n"
            + self._SECOND_HEADER + self._SECOND_FAIL_ROW + "\n结论：PASS\n"
        )
        result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("额外验收表", result.stdout)
        self.assertIn("行号：14", result.stdout)
        self.assertIn("缺少表头分隔行", result.stdout)
        self.assertIn("不支持跨表聚合验证", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)
        # 第二表表头不得被并入首表数据行而产生「验收 ID 无效」这类虚假诊断。
        self.assertNotIn("验收 ID 无效", result.stdout)

        # DONE 下更危险：旧实现会打印「DONE 完整性检查通过」。必须既不 PASS 也不宣称 DONE 通过。
        done = self.run_check(
            content, "--task-id", "TASK-001", "--task-status", "DONE", "--acceptance-id", "AC-001"
        )
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertNotIn("DONE 完整性检查通过", done.stdout)
        self.assertNotIn("未执行 DONE 完整性检查", done.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", done.stdout)

        # 对照：补上分隔行后仍应作为额外验收表被检出，但不再带「缺少表头分隔行」限定。
        complete = (
            self._head() + self._MAIN_TABLE + "\n## 补充验收\n\n"
            + self._SECOND_HEADER + "| --- | --- | --- | --- | --- | --- |\n"
            + self._SECOND_FAIL_ROW + "\n结论：PASS\n"
        )
        result = self.run_check(complete, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("额外验收表", result.stdout)
        self.assertNotIn("缺少表头分隔行", result.stdout)
        # 对照：首表自身存在确定 FAIL 时，必须是 FAIL(1)，不得降级为 UNKNOWN。
        fail_first = complete.replace(
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |",
            "| AC-001 | pytest -q | 1 | FAIL | artifact.log | 失败 |",
        )
        result = self.run_check(fail_first, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)

    def test_preceding_suspected_acceptance_table_never_passes(self) -> None:
        # 主表之前的「验收编号 | 结论」简表同样是验收记录，不能在假 PASS 中被无视。
        simple = "| 验收编号 | 结论 |\n| --- | --- |\n| AC-000 | FAIL |\n"
        content = self._head() + simple + "\n" + self._MAIN_TABLE + "\n结论：PASS\n"
        result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("主验收表之前存在 1 个疑似验收记录表", result.stdout)
        self.assertIn("行号：8", result.stdout)
        self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

        # 对照：同一简表若只是普通统计（无验收语义列名），不得触发。
        unrelated = "| 模块 | 状态 |\n| --- | --- |\n| core | ok |\n"
        content = self._head() + unrelated + "\n" + self._MAIN_TABLE + "\n结论：PASS\n"
        result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertNotIn("主验收表之前存在", result.stdout)

    def test_design_tables_are_not_execution_acceptance(self) -> None:
        # 含「用例 ID」但只有前瞻语义列（预期/前置/步骤）的表格是设计清单，不是执行结论。
        design_tables = (
            "| 用例 ID | 预期结果 |\n| --- | --- |\n| TC-001 | 返回 200 |\n",
            "| 用例 ID | 前置条件 | 步骤 | 预期结果 |\n| --- | --- | --- | --- |\n| TC-001 | 已登录 | 点击 | 跳转成功 |\n",
            "| 用例 ID | 预期 |\n| --- | --- |\n| TC-001 | 无异常 |\n",
            "| Case ID | Expected Result |\n| --- | --- |\n| TC-1 | 200 OK |\n",
        )
        for table in design_tables:
            content = self._head() + self._MAIN_TABLE + "\n## 用例设计\n\n" + table + "\n结论：PASS\n"
            result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertEqual(result.returncode, 0, (table, result.stdout))
            self.assertNotIn("额外验收表", result.stdout)
        # 对照：换成实际结论语义列且含 FAIL，就必须检出——证明判定依据是结果语义而非「用例 ID」。
        actual_tables = (
            "| 用例 ID | 实际结论 |\n| --- | --- |\n| TC-9 | FAIL |\n",
            "| Case ID | Result |\n| --- | --- |\n| TC-9 | FAIL |\n",
        )
        for table in actual_tables:
            content = self._head() + self._MAIN_TABLE + "\n## 执行结果\n\n" + table + "\n结论：PASS\n"
            result = self.run_check(content, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertEqual(result.returncode, 2, (table, result.stdout))
            self.assertIn("额外验收表", result.stdout)
            self.assertNotIn("== 证据门禁: PASS ==", result.stdout)

    def test_fenced_tables_are_excluded_from_acceptance_scan(self) -> None:
        # 围栏代码块内的示例表格不是真实验收记录，不得计入执行证据扫描。
        table = "| 用例 ID | 结论 |\n| --- | --- |\n| AC-900 | FAIL |\n"
        for fence in ("```", "~~~"):
            fenced = self._head() + self._MAIN_TABLE + f"\n## 示例\n\n{fence}text\n" + table + f"{fence}\n\n结论：PASS\n"
            result = self.run_check(fenced, "--task-id", "TASK-001", "--task-status", "REVIEW")
            self.assertEqual(result.returncode, 0, (fence, result.stdout))
            self.assertIn("== 证据门禁: PASS ==", result.stdout)
        # 对照：同一张表不加围栏就是真实的额外验收表，必须检出——证明围栏判定确实生效。
        plain = self._head() + self._MAIN_TABLE + "\n## 执行结果\n\n" + table + "\n结论：PASS\n"
        result = self.run_check(plain, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("额外验收表", result.stdout)

    def test_extra_acceptance_table_ruling_is_unknown(self) -> None:
        # 契约裁定（非缺陷修复）：额外验收表含 FAIL 时返回 UNKNOWN(2)，
        # 因为门禁不做跨表聚合验证，无法确认该失败是否属于本任务判定范围。
        # 曾有 FAIL(1) 的不同期望，契约以 UNKNOWN(2) 为准。
        adjacent = self._head() + self._MAIN_TABLE + self._SECOND_HEADER + self._SECOND_FAIL_ROW + "\n结论：PASS\n"
        result = self.run_check(adjacent, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("== 证据门禁: UNKNOWN ==", result.stdout)
        self.assertIn("不支持跨表聚合验证", result.stdout)
        self.assertNotIn("== 证据门禁: FAIL ==", result.stdout)
        # 裁定的边界：正式主表中可靠解析出的 FAIL 仍必须是 FAIL(1)，UNKNOWN 不得吞掉确定的失败。
        fail_first = adjacent.replace(
            "| AC-001 | python -V | 0 | PASS | artifact.log | 无 |",
            "| AC-001 | pytest -q | 1 | FAIL | artifact.log | 失败 |",
        )
        result = self.run_check(fail_first, "--task-id", "TASK-001", "--task-status", "REVIEW")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("== 证据门禁: FAIL ==", result.stdout)


if __name__ == "__main__":
    unittest.main()
