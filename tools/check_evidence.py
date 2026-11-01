# -*- coding: utf-8 -*-
"""只读验证证据门禁。

检查现有 ``templates/EVIDENCE-template.md.template`` 形态的 Markdown 记录，
不修改任务状态、不写回证据，也不判断测试是否覆盖了完整需求。

必需输入：证据文件路径。
``--task-status`` 决定是否执行 DONE 完整性检查：省略时不判 PASS，返回 2（UNKNOWN），
避免把「未执行的检查」呈现为通过。

退出码：0=PASS；1=FAIL；2=UNKNOWN/NOT_CHECKED（输入不足以作出判断）。
严重度：FAIL > UNKNOWN > PASS；同时存在两类结论时返回 1。

未完成语义：
- 行结论 NOT_RUN/BLOCKED 且原因有效：非 DONE 状态记 UNKNOWN(2)，不呈现为 PASS；
  DONE 状态由完整性检查判为 FAIL(1)。
- 行结论 N/A 且原因有效：非必要验收可保留通过；被登记为必要验收时判 FAIL(1)。
- 总结论 NOT_RUN/BLOCKED/N/A：DONE 状态判 FAIL(1)，其余状态记 UNKNOWN(2)。

表格边界：支持 ID 列别名（验收编号/用例 ID 等），
与主表无空行相邻的第二个验收表按表头+分隔行切分，检出即记 UNKNOWN。
门禁不支持跨表聚合验证，检出额外验收表不代表已覆盖其中的记录。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ALLOWED = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "N/A"}
# 未完成类结论：存在即说明验证没有真正完成，绝不能呈现为 PASS。
UNFINISHED = {"NOT_RUN", "BLOCKED", "N/A"}
ID_COLUMN_TOKENS = ("验收 ID", "验收编号", "用例 ID", "Acceptance", "Case ID")
# 结果语义列：报告「已经发生了什么」，属验证范畴。
RESULT_COLUMN_TOKENS = ("结论", "结果", "Result", "Outcome", "实际")
# 前瞻/设计语义列：描述「应当发生什么」，属需求设计范畴，不得当成执行结论。
PROSPECTIVE_COLUMN_TOKENS = ("预期", "期望", "Expected", "Expect", "前置", "Precondition")
COMMAND_COLUMN_TOKENS = ("命令", "步骤", "Command", "Step")
EXIT_COLUMN_TOKENS = ("退出码", "Exit")
EVIDENCE_COLUMN_TOKENS = ("证据", "Evidence")
LIMIT_COLUMN_TOKENS = ("限制", "Limit")
# 主表必须六类列齐全：ID + 命令/步骤 + 退出码 + 结论/结果 + 证据 + 限制。
# 其中结果列须为「结果语义」，不能用「预期结果」这类前瞻列充数（见 _is_result_column）。
FENCE_RE = re.compile(r"^(`{3,}|~{3,})")
PLACEHOLDER = re.compile(r"^\s*<[^>]+>\s*$")
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
MISSING_MARKERS = {"", "N/A", "NA", "NONE", "NULL", "无", "未填写", "未填"}
EXTERNAL_PREFIXES = ("http://", "https://", "s3://", "gs://", "az://", "artifact://", "oci://")
TIMEZONE_RE = re.compile(
    r"(?:\b(?:UTC|GMT)\b|[zZ]\b|[+-]\d{2}:?\d{2}\b|\b[A-Za-z][A-Za-z0-9_-]*/[A-Za-z0-9_+.-]+\b)"
)
DATE_CONTENT_RE = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,4}")
CLOCK_CONTENT_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")
TIMESTAMP_RE = re.compile(
    r"(?P<year>\d{4})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})"
    r"(?:T|\s+)"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?\s*"
    r"(?P<timezone>UTC|GMT|Z|[+-]\d{2}:?\d{2}|[A-Za-z][A-Za-z0-9_-]*/[A-Za-z0-9_+.-]+)",
    re.I,
)
NUMERIC_TZ_RE = re.compile(r"(?P<sign>[+-])(?P<hour>\d{2}):?(?P<minute>\d{2})$")
IANA_TZ_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*/[A-Za-z0-9_+.-]+$")
MANUAL_STEP_RE = re.compile(r"(?:人工检查|人工核对|人工审查|manual(?:\s+check)?)", re.I)


def _value(lines: list[str], labels: tuple[str, ...]) -> str:
    for line in lines:
        for label in labels:
            match = re.match(rf"^\s*{re.escape(label)}\s*[:：]\s*(.*?)\s*$", line, re.I)
            if match:
                return match.group(1)
    return ""


def _is_placeholder(value: str) -> bool:
    return not value or bool(PLACEHOLDER.fullmatch(value))


def _is_missing(value: str) -> bool:
    stripped = value.strip()
    return _is_placeholder(stripped) or stripped.upper() in MISSING_MARKERS or stripped in MISSING_MARKERS


def _has_reason(value: str) -> bool:
    return not _is_missing(value)


def _is_external_reference(value: str) -> bool:
    return value.strip().lower().startswith(EXTERNAL_PREFIXES)


def _resolve_reference(base_dir: str, value: str) -> str:
    value = value.strip().strip("<>")
    return value if os.path.isabs(value) else os.path.join(base_dir, value)


def _has_timezone(value: str) -> bool:
    return bool(TIMEZONE_RE.search(value))


def _has_date(value: str) -> bool:
    return bool(DATE_CONTENT_RE.search(value))


def _has_clock(value: str) -> bool:
    return bool(CLOCK_CONTENT_RE.search(value))


def _validate_timestamp(value: str) -> list[str]:
    """Validate common timestamp forms without requiring a system tz database."""
    issues = []
    if not _has_date(value):
        issues.append("UNKNOWN: 时间记录缺少可识别的日期。")
    if not _has_clock(value):
        issues.append("UNKNOWN: 时间记录缺少可识别的具体时刻。")
    if not _has_timezone(value):
        issues.append("UNKNOWN: 时间记录缺少可识别的时区。")
    if issues:
        return issues

    match = TIMESTAMP_RE.fullmatch(value.strip())
    if not match:
        return ["UNKNOWN: 时间记录格式无法可靠解析。"]

    fields = match.groupdict()
    try:
        dt.date(int(fields["year"]), int(fields["month"]), int(fields["day"]))
    except ValueError:
        issues.append("UNKNOWN: 时间记录的日期取值非法。")
    try:
        dt.time(int(fields["hour"]), int(fields["minute"]), int(fields["second"] or 0))
    except ValueError:
        issues.append("UNKNOWN: 时间记录的具体时刻取值非法。")

    timezone = fields["timezone"]
    numeric = NUMERIC_TZ_RE.fullmatch(timezone)
    if numeric:
        offset_hour = int(numeric.group("hour"))
        offset_minute = int(numeric.group("minute"))
        if offset_minute > 59 or offset_hour > 14 or (offset_hour == 14 and offset_minute != 0):
            issues.append("UNKNOWN: 时间记录的 UTC 偏移量非法。")
        else:
            try:
                delta = dt.timedelta(hours=offset_hour, minutes=offset_minute)
                if numeric.group("sign") == "-":
                    delta = -delta
                dt.timezone(delta)
            except (OverflowError, ValueError):
                issues.append("UNKNOWN: 时间记录的 UTC 偏移量无法可靠解析。")
    elif timezone.upper() not in {"UTC", "GMT", "Z"} and not IANA_TZ_RE.fullmatch(timezone):
        issues.append("UNKNOWN: 时间记录的时区标记无法可靠解析。")
    return issues


def _cells_of(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_row_line(line: str) -> bool:
    return line.lstrip().startswith("|") and "|" in line[1:]


def _has_token(cells: list[str], tokens: tuple[str, ...]) -> bool:
    return any(token.lower() in cell.lower() for token in tokens for cell in cells)


def _find_column(headers: list[str], tokens: tuple[str, ...]) -> int:
    for index, cell in enumerate(headers):
        if any(token.lower() in cell.lower() for token in tokens):
            return index
    raise StopIteration


def _is_result_column(cell: str) -> bool:
    """判断某列是否为「结果语义」列（对已发生结果的报告）。

    「预期结果」「期望值」「Expected Result」「前置条件」属前瞻/设计语义，
    即使字面含「结果」也不算执行结论，必须先排除。
    """
    text = cell.lower()
    if any(token.lower() in text for token in PROSPECTIVE_COLUMN_TOKENS):
        return False
    return any(token.lower() in text for token in RESULT_COLUMN_TOKENS)


def _is_acceptance_header(cells: list[str]) -> bool:
    """宽松识别「像验收表」的表头：ID 列别名 + 至少一个结果语义列。

    要求存在结果语义列（结论/结果/实际结论 等）而非任意语义列，
    使「用例 ID｜预期结果｜前置条件」这类测试设计清单不被当成执行验收表；
    同时「用例 ID｜实际结论」「验收编号｜结论」等真实记录仍能被检出。
    """
    return _has_token(cells, ID_COLUMN_TOKENS) and any(_is_result_column(cell) for cell in cells)


def _is_full_acceptance_header(cells: list[str]) -> bool:
    """主表识别：六类验收列齐全（结果列须为结果语义，不得用预期列充数）。"""
    return (
        _has_token(cells, ID_COLUMN_TOKENS)
        and _has_token(cells, COMMAND_COLUMN_TOKENS)
        and _has_token(cells, EXIT_COLUMN_TOKENS)
        and any(_is_result_column(cell) for cell in cells)
        and _has_token(cells, EVIDENCE_COLUMN_TOKENS)
        and _has_token(cells, LIMIT_COLUMN_TOKENS)
    )


def _find_result_column(headers: list[str]) -> int:
    for index, cell in enumerate(headers):
        if _is_result_column(cell):
            return index
    raise StopIteration


def _is_separator_line(lines: list[str], index: int) -> bool:
    if index < 0 or index >= len(lines) or not _is_row_line(lines[index]):
        return False
    cells = _cells_of(lines[index])
    return bool(cells) and all(set(cell) <= {"-", ":", " "} for cell in cells)


def _is_complete_table_start(lines: list[str], index: int) -> bool:
    """完整验收表开始：验收表头 + 紧随其后的分隔行。"""
    if index < 0 or index >= len(lines) or not _is_row_line(lines[index]):
        return False
    if not _is_acceptance_header(_cells_of(lines[index])):
        return False
    return _is_separator_line(lines, index + 1)


def _fenced_lines(lines: list[str]) -> set[int]:
    """返回处于 Markdown 围栏代码块内（含围栏定界行）的行号集合。

    代码块内的表格是语法示例，不参与执行证据扫描。
    """
    fenced: set[int] = set()
    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        match = FENCE_RE.match(line.strip())
        if fence is None:
            if match:
                token = match.group(1)
                fence = (token[0], len(token))
                fenced.add(index)
        else:
            fenced.add(index)
            if match:
                token = match.group(1)
                if token[0] == fence[0] and len(token) >= fence[1]:
                    fence = None
    return fenced


def _parse_rows(
    lines: list[str],
) -> tuple[list[dict[str, str]], list[str], list[int], list[int], list[int]]:
    """解析首个完整验收表，并返回疑似验收表的行号（1 基）。

    返回值第三~五项分别为：主表之后的完整额外验收表、主表之后格式不完整
    （缺表头分隔行）的疑似验收表、主表之前的疑似验收记录表。

    门禁不支持跨表聚合验证：任一类存在都必须如实报 UNKNOWN，
    不允许因为「表不完整 / 位置在表前」就静默忽略（否则等于假 PASS）。
    """
    errors: list[str] = []
    fenced = _fenced_lines(lines)
    header_index = None
    headers: list[str] = []
    for index, line in enumerate(lines):
        if index in fenced or not _is_row_line(line):
            continue
        cells = _cells_of(line)
        if _is_full_acceptance_header(cells):
            header_index, headers = index, cells
            break
    if header_index is None:
        return [], ["缺少验收表（需要包含验收 ID、命令/步骤、退出码、结论、证据路径与限制列）。"], [], [], []
    try:
        id_col = _find_column(headers, ID_COLUMN_TOKENS)
        command_col = _find_column(headers, COMMAND_COLUMN_TOKENS)
        exit_col = _find_column(headers, EXIT_COLUMN_TOKENS)
        result_col = _find_result_column(headers)
        evidence_col = _find_column(headers, EVIDENCE_COLUMN_TOKENS)
        limit_col = _find_column(headers, LIMIT_COLUMN_TOKENS)
    except StopIteration:
        return [], ["验收表缺少命令、退出码、结论、证据路径或限制列。"], [], [], []

    def acceptance_like(index: int) -> bool:
        return (
            index not in fenced
            and _is_row_line(lines[index])
            and _is_acceptance_header(_cells_of(lines[index]))
        )

    rows = []
    reading_rows = False
    for offset in range(header_index + 1, len(lines)):
        line = lines[offset]
        # 任何「像验收表」的行（无论分隔行是否齐全）都停止本表取值：
        # 既避免把下一张表的表头当作数据行，也避免漏掉格式不完整的表。
        if acceptance_like(offset):
            break
        if offset in fenced or not _is_row_line(line):
            if reading_rows:
                break
            continue
        cells = _cells_of(line)
        if not cells or all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if len(cells) <= max(id_col, command_col, exit_col, result_col, evidence_col, limit_col):
            errors.append("验收表存在列数不足的行。")
            continue
        reading_rows = True
        rows.append({
            "id": cells[id_col],
            "command": cells[command_col],
            "exit": cells[exit_col],
            "result": cells[result_col].upper(),
            "evidence": cells[evidence_col],
            "limit": cells[limit_col],
        })
    if not rows:
        errors.append("验收表没有可检查的验收记录。")
    # 主表之后（完整 / 不完整）与主表之前的疑似验收表，都不能默认为无遗漏。
    extra_complete: list[int] = []
    extra_incomplete: list[int] = []
    preceding: list[int] = []
    for index in range(len(lines)):
        if index == header_index or not acceptance_like(index):
            continue
        if index < header_index:
            preceding.append(index + 1)
        elif _is_complete_table_start(lines, index):
            extra_complete.append(index + 1)
        else:
            extra_incomplete.append(index + 1)
    return rows, errors, extra_complete, extra_incomplete, preceding


def check(path: str, expected_task: str | None, expected_acceptance: list[str], task_status: str | None,
          required_paths: list[str]) -> tuple[int, list[str]]:
    diagnostics: list[str] = []
    status = task_status.upper() if task_status else None
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return 1, [f"FAIL: 无法读取证据文件: {exc}"]

    base_dir = os.path.dirname(os.path.abspath(path))
    task = _value(lines, ("Task", "任务 ID", "任务"))
    timestamp = _value(lines, ("Time", "时间", "时间与时区"))
    baseline = _value(lines, ("Baseline", "代码版本", "版本"))
    environment = _value(lines, ("Environment", "环境"))
    if _is_missing(task):
        diagnostics.append("UNKNOWN: 缺少可核验的任务 ID。")
    elif any(char.isspace() for char in task) or "|" in task:
        diagnostics.append(f"FAIL: 任务 ID 格式不可识别: {task}")
    if expected_task and task != expected_task:
        diagnostics.append(f"FAIL: 任务 ID {task!r} 与期望值 {expected_task!r} 不一致。")
    if _is_missing(timestamp):
        diagnostics.append("UNKNOWN: 缺少时间记录。")
    else:
        diagnostics.extend(_validate_timestamp(timestamp))
    if _is_missing(baseline):
        diagnostics.append("UNKNOWN: 未记录代码版本或工作区标识。")
    if _is_missing(environment):
        diagnostics.append("UNKNOWN: 未记录执行环境。")

    rows, parse_errors, extra_complete, extra_incomplete, preceding = _parse_rows(lines)
    diagnostics.extend(f"FAIL: {error}" for error in parse_errors)
    if preceding:
        diagnostics.append(
            f"UNKNOWN: 主验收表之前存在 {len(preceding)} 个疑似验收记录表"
            f"（行号：{', '.join(str(n) for n in preceding)}）；"
            "门禁只解析首个完整验收表，无法判定这些记录是否已通过，因此不返回 PASS。"
        )
    extra_headers = sorted(extra_complete + extra_incomplete)
    if extra_headers:
        qualifier = (
            f"；其中 {len(extra_incomplete)} 个缺少表头分隔行，按疑似验收表保守处理"
            if extra_incomplete else ""
        )
        diagnostics.append(
            f"UNKNOWN: 检测到 {len(extra_headers)} 个额外验收表"
            f"（行号：{', '.join(str(n) for n in extra_headers)}{qualifier}）；"
            "门禁只解析首个连续验收表，不支持跨表聚合验证，无法判定这些验收记录是否已通过，因此不返回 PASS。"
        )
    seen_ids = set()
    row_results = []
    for row in rows:
        rid = row["id"]
        if _is_missing(rid) or not ID_RE.fullmatch(rid):
            diagnostics.append(f"FAIL: 验收 ID 无效: {rid!r}")
        if rid in seen_ids:
            diagnostics.append(f"FAIL: 验收 ID 重复: {rid}")
        seen_ids.add(rid)
        result = row["result"]
        if result not in ALLOWED:
            diagnostics.append(f"FAIL: {rid} 的结论不在允许集合: {result!r}")
        elif result == "FAIL":
            diagnostics.append(f"FAIL: {rid} 验收结论为 FAIL。")
        evidence_known = False
        if not _is_missing(row["evidence"]):
            if _is_external_reference(row["evidence"]):
                diagnostics.append(f"UNKNOWN: {rid} 的外部证据索引无法在本地验证: {row['evidence']}")
            else:
                evidence_path = _resolve_reference(base_dir, row["evidence"])
                if not os.path.exists(evidence_path):
                    diagnostics.append(f"FAIL: {rid} 的证据路径不存在: {row['evidence']}")
                else:
                    evidence_known = True
        if result == "PASS":
            if _is_missing(row["command"]):
                diagnostics.append(f"FAIL: {rid} 标记 PASS 但没有执行命令/步骤。")
            exit_code = row["exit"].strip()
            manual_na = exit_code.upper() in {"N/A", "NA"} and MANUAL_STEP_RE.search(row["command"]) and _has_reason(row["limit"])
            if exit_code != "0" and not manual_na:
                diagnostics.append(f"FAIL: {rid} 标记 PASS 但退出码与执行语义不一致。")
            if _is_missing(row["evidence"]):
                diagnostics.append(f"FAIL: {rid} 标记 PASS 但没有证据路径。")
            elif manual_na and not evidence_known and not _is_external_reference(row["evidence"]):
                diagnostics.append(f"FAIL: {rid} 的人工检查证据不可定位。")
        elif result in UNFINISHED and not _has_reason(row["limit"]):
            diagnostics.append(f"FAIL: {rid} 为 {result} 但没有有效原因或限制说明。")
        elif result == "N/A" and rid in expected_acceptance:
            # 契约 8：有理由的非必要 N/A 可保留允许行为，必要验收的 N/A 不能视为通过。
            diagnostics.append(f"FAIL: 必要验收 {rid} 为 N/A，不能视为通过。")
        elif result in {"NOT_RUN", "BLOCKED"} and status != "DONE":
            # 契约 4：非 DONE 状态下，原因有效的未执行/阻塞记录不是失败，但绝不能呈现为 PASS。
            diagnostics.append(
                f"UNKNOWN: {rid} 为 {result}，验证未完成，不能作为通过依据（原因：{row['limit']}）。"
            )
        row_results.append(result)

    missing_acceptance = [rid for rid in expected_acceptance if rid not in seen_ids]
    diagnostics.extend(f"FAIL: 缺少必要验收记录: {rid}" for rid in missing_acceptance)
    for required in required_paths:
        if _is_external_reference(required):
            diagnostics.append(f"UNKNOWN: 外部必要证据索引无法在本地验证: {required}")
        elif not os.path.exists(_resolve_reference(base_dir, required)):
            diagnostics.append(f"FAIL: 必要证据路径不存在: {required}")

    overall = _value(lines, ("结论", "Conclusion"))
    if overall:
        overall = overall.upper()
        if overall not in ALLOWED:
            diagnostics.append(f"FAIL: 总结论不在允许集合: {overall}")
        elif overall == "FAIL":
            diagnostics.append("FAIL: 总结论明确为 FAIL。")
        elif overall == "PASS" and any(result in {"FAIL", "BLOCKED", "NOT_RUN"} for result in row_results):
            diagnostics.append("FAIL: 总结论 PASS 与验收行存在非 PASS 结论矛盾。")
        elif overall in UNFINISHED:
            # 总结论自述未完成：与 DONE 状态直接矛盾（确定失败）；其余状态不得呈现为 PASS。
            if status == "DONE":
                diagnostics.append(f"FAIL: 总结论为 {overall}，与任务状态 DONE 矛盾，验证未完成。")
            else:
                diagnostics.append(f"UNKNOWN: 总结论为 {overall}，验证未完成，门禁不能据此判定 PASS。")

    if status == "DONE":
        if not expected_acceptance:
            diagnostics.append("UNKNOWN: 未提供必要验收集合，无法判断 DONE 是否覆盖完整 DoD。")
        else:
            required_results = {row["id"]: row["result"] for row in rows if row["id"] in expected_acceptance}
            incomplete = [
                rid for rid in expected_acceptance
                if rid in required_results and required_results[rid] != "PASS"
            ]
            if incomplete:
                diagnostics.append(f"FAIL: 必要验收未通过或不适用，不能 DONE: {', '.join(incomplete)}")
            optional_blockers = [
                row["id"] for row in rows
                if row["id"] not in expected_acceptance and row["result"] in {"FAIL", "BLOCKED", "NOT_RUN"}
            ]
            if optional_blockers:
                diagnostics.append(f"FAIL: 存在未处置的非必要失败/阻塞/未执行记录: {', '.join(optional_blockers)}")
    elif status is None:
        diagnostics.append("UNKNOWN: 未提供任务状态，未执行 DONE 完整性检查；门禁不能据此判定 PASS。")

    if any(item.startswith("FAIL:") for item in diagnostics):
        return 1, diagnostics
    if any(item.startswith("UNKNOWN:") for item in diagnostics):
        return 2, diagnostics
    if status == "DONE":
        return 0, ["PASS: 证据结构与 DONE 完整性检查通过；不代表需求覆盖充分或替代独立 Review。"]
    return 0, [f"PASS: 证据结构检查通过（任务状态 {status}）；未执行 DONE 完整性检查。"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", help="现有证据 Markdown 文件")
    parser.add_argument("--task-id", help="期望的任务 ID")
    parser.add_argument("--acceptance-id", action="append", default=[], help="必须出现的验收 ID；task-status=DONE 时作为必要验收集合，可重复")
    parser.add_argument(
        "--task-status", type=str.upper, choices=["DONE", "REVIEW", "IN_PROGRESS", "BLOCKED"],
        help="任务当前状态。DONE 会执行完整性检查；省略时不判 PASS 并返回 2（UNKNOWN）。",
    )
    parser.add_argument("--require-path", action="append", default=[], help="必须存在的证据路径；相对路径以证据文件目录为基准，可重复")
    args = parser.parse_args(argv)
    code, diagnostics = check(args.evidence, args.task_id, args.acceptance_id, args.task_status, args.require_path)
    for item in diagnostics:
        print(item)
    print(f"== 证据门禁: {('PASS' if code == 0 else 'FAIL' if code == 1 else 'UNKNOWN')} ==")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
