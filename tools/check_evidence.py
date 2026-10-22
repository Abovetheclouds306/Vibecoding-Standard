# -*- coding: utf-8 -*-
"""只读验证证据门禁。

检查现有 ``templates/EVIDENCE-template.md.template`` 形态的 Markdown 记录，
不修改任务状态、不写回证据，也不判断测试是否覆盖了完整需求。

退出码：0=PASS；1=FAIL；2=UNKNOWN/NOT_CHECKED（输入不足以作出判断）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ALLOWED = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "N/A"}
PLACEHOLDER = re.compile(r"^\s*<[^>]+>\s*$")
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


def _value(lines: list[str], labels: tuple[str, ...]) -> str:
    for line in lines:
        for label in labels:
            match = re.match(rf"^\s*{re.escape(label)}\s*[:：]\s*(.*?)\s*$", line, re.I)
            if match:
                return match.group(1)
    return ""


def _is_placeholder(value: str) -> bool:
    return not value or bool(PLACEHOLDER.fullmatch(value))


def _parse_rows(lines: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    header_index = None
    headers: list[str] = []
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("|") or "|" not in line[1:]:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if any("验收 ID" in cell or "Acceptance" in cell for cell in cells):
            header_index, headers = index, cells
            break
    if header_index is None:
        return [], ["缺少验收表（需要包含‘验收 ID’或‘Acceptance’列）。"]
    try:
        id_col = next(i for i, cell in enumerate(headers) if "验收 ID" in cell or "Acceptance" in cell)
        command_col = next(i for i, cell in enumerate(headers) if "命令" in cell or "Command" in cell)
        exit_col = next(i for i, cell in enumerate(headers) if "退出码" in cell or "Exit" in cell)
        result_col = next(i for i, cell in enumerate(headers) if "结论" in cell or "Result" in cell)
        evidence_col = next(i for i, cell in enumerate(headers) if "证据" in cell or "Evidence" in cell)
        limit_col = next(i for i, cell in enumerate(headers) if "限制" in cell or "Limit" in cell)
    except StopIteration:
        return [], ["验收表缺少命令、退出码、结论、证据路径或限制列。"]

    rows = []
    for line in lines[header_index + 1 :]:
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if len(cells) <= max(id_col, command_col, exit_col, result_col, evidence_col, limit_col):
            errors.append("验收表存在列数不足的行。")
            continue
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
    return rows, errors


def check(path: str, expected_task: str | None, expected_acceptance: list[str], task_status: str | None,
          required_paths: list[str]) -> tuple[int, list[str]]:
    diagnostics: list[str] = []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError as exc:
        return 1, [f"无法读取证据文件: {exc}"]

    task = _value(lines, ("Task", "任务 ID", "任务"))
    baseline = _value(lines, ("Baseline", "代码版本", "版本"))
    environment = _value(lines, ("Environment", "环境"))
    if _is_placeholder(task):
        diagnostics.append("UNKNOWN: 缺少可核验的任务 ID。")
    elif any(char.isspace() for char in task) or "|" in task:
        diagnostics.append(f"FAIL: 任务 ID 格式不可识别: {task}")
    if expected_task and task != expected_task:
        diagnostics.append(f"FAIL: 任务 ID {task!r} 与期望值 {expected_task!r} 不一致。")
    if _is_placeholder(baseline):
        diagnostics.append("UNKNOWN: 未记录代码版本或工作区标识。")
    if _is_placeholder(environment):
        diagnostics.append("UNKNOWN: 未记录执行环境。")

    rows, parse_errors = _parse_rows(lines)
    diagnostics.extend(f"FAIL: {error}" for error in parse_errors)
    seen_ids = set()
    row_results = []
    for row in rows:
        rid = row["id"]
        if _is_placeholder(rid) or not ID_RE.fullmatch(rid):
            diagnostics.append(f"FAIL: 验收 ID 无效: {rid!r}")
        if rid in seen_ids:
            diagnostics.append(f"FAIL: 验收 ID 重复: {rid}")
        seen_ids.add(rid)
        result = row["result"]
        if result not in ALLOWED:
            diagnostics.append(f"FAIL: {rid} 的结论不在允许集合: {result!r}")
        if result == "PASS":
            if _is_placeholder(row["command"]):
                diagnostics.append(f"FAIL: {rid} 标记 PASS 但没有执行命令/步骤。")
            if row["exit"].strip() != "0":
                diagnostics.append(f"FAIL: {rid} 标记 PASS 但退出码不是 0。")
            if _is_placeholder(row["evidence"]) or row["evidence"].upper() in {"N/A", "无"}:
                diagnostics.append(f"FAIL: {rid} 标记 PASS 但没有证据路径。")
        elif result in {"NOT_RUN", "BLOCKED"} and _is_placeholder(row["limit"]):
            diagnostics.append(f"FAIL: {rid} 为 {result} 但没有原因或限制说明。")
        if row["evidence"] and not _is_placeholder(row["evidence"]) and row["evidence"].upper() not in {"N/A", "无"}:
            evidence_path = row["evidence"].strip().strip("<>")
            if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(path)), evidence_path)):
                diagnostics.append(f"FAIL: {rid} 的证据路径不存在: {row['evidence']}")
        row_results.append(result)

    missing_acceptance = [rid for rid in expected_acceptance if rid not in seen_ids]
    diagnostics.extend(f"FAIL: 缺少必要验收记录: {rid}" for rid in missing_acceptance)
    for required in required_paths:
        if not os.path.exists(required):
            diagnostics.append(f"FAIL: 必要证据路径不存在: {required}")

    overall = _value(lines, ("结论", "Conclusion"))
    if overall:
        overall = overall.upper()
        if overall not in ALLOWED:
            diagnostics.append(f"FAIL: 总结论不在允许集合: {overall}")
        elif overall == "PASS" and any(result != "PASS" for result in row_results):
            diagnostics.append("FAIL: 总结论 PASS 与验收行存在非 PASS 结论矛盾。")

    if task_status and task_status.upper() == "DONE":
        if not rows:
            diagnostics.append("FAIL: DONE 缺少必要验收记录。")
        elif any(result in {"FAIL", "BLOCKED", "NOT_RUN", "N/A"} for result in row_results):
            diagnostics.append("FAIL: DONE 仍存在未通过、阻塞、未执行或不适用的验收记录。")

    if any(item.startswith("FAIL:") for item in diagnostics):
        return 1, diagnostics
    if any(item.startswith("UNKNOWN:") for item in diagnostics):
        return 2, diagnostics
    return 0, ["PASS: 证据字段和验收记录满足门禁；不代表需求覆盖充分或替代独立 Review。"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", help="现有证据 Markdown 文件")
    parser.add_argument("--task-id", help="期望的任务 ID")
    parser.add_argument("--acceptance-id", action="append", default=[], help="必须出现的验收 ID，可重复")
    parser.add_argument("--task-status", choices=["DONE", "REVIEW", "IN_PROGRESS", "BLOCKED"])
    parser.add_argument("--require-path", action="append", default=[], help="必须存在的证据路径，可重复")
    args = parser.parse_args(argv)
    code, diagnostics = check(args.evidence, args.task_id, args.acceptance_id, args.task_status, args.require_path)
    for item in diagnostics:
        print(item)
    print(f"== 证据门禁: {('PASS' if code == 0 else 'FAIL' if code == 1 else 'UNKNOWN')} ==")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
