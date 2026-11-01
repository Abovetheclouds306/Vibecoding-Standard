#!/usr/bin/env python3
"""vb_init.py — Vibecoding Skill 受保护初始化（PbC：默认 dry-run，--apply 才落盘）。

约束（与 SKILL.md 铁律一致）：
1. 从不编辑 CLAUDE.md；从不改写 AGENTS.md 标记块之外的内容。
2. 重复执行必须幂等：第二次全部 unchanged，不新增/不改动任何文件。
3. 写入 tracked 文件前若工作区脏，需 --allow-dirty。
4. 标准副本校验不过则拒绝初始化（退出码 1），不写任何文件。
5. 写盘前做可预见检查（目标类型冲突、路径不得越出项目目录）；任何检查不过即拒绝，且尚未写任何文件。
6. 所有写盘经 WriteJournal 登记：**先登记恢复记录再写入**；单条写入先写同目录临时文件，
   再 `os.replace` 原子替换（同卷语义），因此单条写入失败不会留下半截目标文件。
   可控异常按逆序回滚本次写入（只回滚本进程创建/修改、且当前内容仍等于本进程写入值的文件；
   不删除用户原有文件），失败返回非零退出码并打印诊断；无法还原时输出 `ResidualRisk`
   与受影响路径及实际残留状态，且**不再宣称"已全部回滚"**。
7. 每次实际写入前重新核对目标真实位置：越出项目目录、或预检后该路径真实位置发生变化
   （被替换为符号链接 / Junction / 其他重解析点），一律拒绝继续初始化并非零退出。
   回滚、以及单条写入失败后的就地补偿（还原 / 撤销新建）同样受此约束，
   不跟随被替换的路径去删改项目外数据。
   **边界**：这是把 TOCTOU 窗口压到最小，**不是消除**——预检与写入之间仍存在极短窗口，
   `SIGKILL` / 断电 / 文件系统自身非原子行为无法由脚本保证，因此不做跨文件原子提交。

退出码：0 = 成功/无需变更（含 `--update-block` 已按授权更新块）；
        1 = 拒绝或出错（含已完成回滚、或部分回滚仍有残留的失败）；
        2 = 仍需人工决定（标记块 differs 且未获 `--update-block` 授权）。

「接入缺失」语义（F-2）：本脚本只使用**已安装技能自带的 vendor 副本**作为规范真值源，
从不把整份规范复制进项目。因此它同时要求：vendor 实际存在、可读、且与签收版本校验一致；
任一不满足即拒绝初始化并说明缺什么。**不宣称"未安装技能也能使用完整规范"。**
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

SKILL_VERSION = "0.1.0"
STANDARD_VERSION = "1.2.7"
STANDARD_SIGNOFF = "ce5b361cf13ae373094abe67eb9ce7a6e22ecb8f"
STANDARD_RELEASE = "fd9750f3e6c4c2105cf253d5f7d6494f0f373fdf"
STANDARD_ZIP_SHA = "0ce2a06cf506904cca4e0597240d43f5e869ee9845d7b508bc83a9fd2745dd38"

BEGIN = "<!-- vibecoding:begin"
END = "<!-- vibecoding:end -->"

BLOCK = """<!-- vibecoding:begin skill={sv} standard={std} -->
## 工程纪律（Vibecoding v{std}）

本项目遵循 Vibecoding Standard v{std}。以下为不可省略的最低动作，细节见 `.vibecoding/` 与所用的 Agent Skill `vibecoding`。

- **唯一规则真值源**：Vibecoding Standard v{std} 正文，只读，与签收版本逐字节相同。规则改动只能回到标准仓库发版，不得就地修改。
  - **规范位置**：以 `.vibecoding/config.json` 的 `standard_vendor_path` 字段为准；该目录须含 `AI_PROJECT_STANDARD.md` 与 `MANIFEST.sha256`。
  - **本次初始化解算**：`{vendor_path}`（{vendor_condition}）。
  - **路径不可读时**：说明技能已卸载或项目已移动。此时**不得假装规范已加载**，也不得引用未读到的条款；须重新安装技能后执行 `vb_init.py --project . --apply` 重定位。
- **开工前**：读 `.vibecoding/config.json` 与 `.vibecoding/HANDOFF.md`；确认分支、HEAD 与工作区状态。
- **验证纪律**：结论必须附命令与**实际退出码**。`0=PASS / 1=FAIL / 2=UNKNOWN`；`2` 既不得当通过，也不得当"跳过"。
- **禁止假 PASS**：未运行写 `NOT_RUN`；为了让门禁变绿而放宽测试断言属禁止行为。
- **证据**：一任务一份 `.vibecoding/evidence/<TASK>.md`，含命令、退出码、证据路径、复查条件。
- **交接**：会话中断前更新 `.vibecoding/HANDOFF.md`；新会话先读它再动手。
- **不改他人改动**：不 `reset` / `checkout --` / `clean` / 强推；发现无关改动保留并报告。
<!-- vibecoding:end -->
"""

HANDOFF_TEMPLATE = """<!-- generated-by: vb_handoff v{sv} -->
# {task} 交接

Updated: {ts}
Task source: 见项目自身任务系统（本文件不复制任务状态）
Workspace: {workspace}
Baseline: {baseline}

## 已完成
{summary}

## 验证
{verify}

## 未完成与阻塞
{blocked}

## 已发生的外部效果
{effects}

## 工作区卫生
{hygiene}

## 恢复步骤
1. `git status --porcelain` 确认未提交改动归属。
2. 读 `.vibecoding/evidence/` 下与本任务相关的证据，核对结论与退出码。
3. 按"未完成与阻塞"逐项继续，不重跑已有副作用的步骤。

## 下一步
{next}
"""

EVIDENCE_TEMPLATE = """<!-- generated-by: vb_gate v{sv} -->
# {task} 验证记录

Task: {task}
Time: {ts}
Baseline: {baseline}
Environment: {env}

| 验收 ID | 命令 / 步骤 | 退出码 | 结论 | 证据路径 | 限制 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | <待执行> | NOT_RUN | NOT_RUN | N/A | 由 vb_gate.py 首次运行时生成 |

结论：NOT_RUN
反向遗漏审查：待人工填写（本任务范围、确认的遗漏与处置）
审查：待人工填写（审查者、版本、结论）
Artifacts: N/A
Recheck Conditions: 代码、依赖或测试变更后需重跑
Cleanup / Recovery: N/A
Release Status: 未涉及
"""


def run(args: list[str], cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, shell=False)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", "command not found: %s" % args[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout: %s" % " ".join(args)


def git(project: str, *args: str) -> tuple[int, str]:
    rc, out, err = run(["git", *args], cwd=project)
    return rc, (out if rc == 0 else err).strip()


def git_state(project: str) -> dict:
    rc, top = git(project, "rev-parse", "--show-toplevel")
    if rc != 0:
        return {"is_repo": False, "root": None, "head": None, "branch": None, "dirty": None, "porcelain": ""}
    _, head = git(project, "rev-parse", "HEAD")
    _, branch = git(project, "rev-parse", "--abbrev-ref", "HEAD")
    _, status = git(project, "status", "--porcelain")
    return {
        "is_repo": True,
        "root": top,
        "head": head,
        "branch": branch,
        "dirty": bool(status),
        "porcelain": status,
    }


def detect_eol(path: str) -> bytes:
    """返回该文件应使用的换行序列：以文件自身为准，避免混行尾。"""
    try:
        data = _read_raw(path)
    except OSError:
        return b"\n"
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    return b"\r\n" if crlf > lf else b"\n"


def _write_raw(path: str, data: bytes) -> None:
    """唯一内容写盘出口（单测可替换以注入可控异常）。"""
    with open(path, "wb") as fh:
        fh.write(data)


def _read_raw(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _replace(src: str, dst: str) -> None:
    """原子替换的提交点（单测可替换以注入「提交阶段失败」）。"""
    os.replace(src, dst)


def _atomic_write(path: str, data: bytes) -> None:
    """同目录临时文件 + 原子替换。

    目标文件在成功替换之前**始终未被打开**，因此单条写入失败不会产生半截目标文件
    （这是 R2-N1 的根因修复）。临时文件与目标同目录 ⇒ 同卷 ⇒ Windows 上 `os.replace`
    为原子替换。不承诺断电 / 强杀下的持久性（已在模块 docstring 声明边界）。
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".vb-w-", suffix=".tmp", dir=directory)
    os.close(fd)
    committed = False
    try:
        _write_raw(tmp, data)
        try:                       # 尽力刷盘；失败不影响"单条写入不产生半截目标"这一性质
            with open(tmp, "rb+") as fh:
                os.fsync(fh.fileno())
        except OSError:
            pass
        _replace(tmp, path)
        committed = True
    finally:
        if not committed:
            try:
                os.remove(tmp)
            except OSError:
                pass


FILE_ATTRIBUTE_REPARSE_POINT = 0x400


def _is_reparse_point(path: str) -> bool:
    """符号链接 / Junction / 其他重解析点。"""
    try:
        if os.path.islink(path):
            return True
    except OSError:
        pass
    isj = getattr(os.path, "isjunction", None)
    if isj is not None:
        try:
            if isj(path):
                return True
        except OSError:
            pass
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT)


def _inside(path_real: str, root_real: str) -> bool:
    return path_real == root_real or path_real.startswith(root_real + os.sep)


def _describe(path: str) -> str:
    """实际残留状态（让 ResidualRisk 报告落在字节数而不是形容词上）。"""
    try:
        if not os.path.exists(path):
            return "不存在"
        if os.path.isdir(path):
            return "目录（未改动）"
        data = _read_raw(path)
        return "%d 字节 sha256=%s" % (len(data), hashlib.sha256(data).hexdigest()[:16])
    except OSError as exc:
        return "不可读(%s)" % exc


class BoundaryError(RuntimeError):
    """目标真实位置越出项目边界，或预检后真实位置被改变（疑似符号链接 / Junction 替换）。"""


class WriteJournal:
    """记录本次运行的文件写入，异常时按逆序回滚。

    契约（R2-N1 / R2-N2 修复后）：
    - **先登记后写**：写入前先把条目（含原始字节）落入 `entries`，所以"写了一半"的文件
      也在回滚范围内，不会被漏掉。
    - **单条原子**：内容先写同目录临时文件，再 `os.replace`；失败时目标文件未被改动。
    - **归属判据**：只回滚"当前内容仍等于本进程写入值"的文件；内容已被他人改动则跳过并报告，
      绝不覆盖他人改动。
    - **边界复核**：每次写入 / 删除 / 回滚 / 单条失败后的补偿还原前重新核对真实位置；
      越界或已被替换则拒绝，不跟随被替换的路径去动项目外数据。
    - **残留如实报告**：无法还原时记入 `residuals`，上层据此禁止打印"已全部回滚"。
    - **不承诺**：SIGKILL / 断电 / 文件系统自身非原子行为下的绝对原子性。
    """

    def __init__(self, root: str | None = None, baseline: dict[str, str] | None = None) -> None:
        self.entries: list[dict] = []
        self.created_dirs: list[str] = []
        self.residuals: list[dict] = []
        self.step = "初始化"
        self.root_abs = os.path.abspath(root) if root else None
        self.root_real = os.path.realpath(root) if root else None
        self.baseline = {os.path.abspath(k): v for k, v in (baseline or {}).items()}

    # ---------------------------------------------------------- 边界守卫
    def guard(self, path: str) -> None:
        """写入 / 删除前的实时边界复核（R2-N2）。不通过即抛 BoundaryError。"""
        if not self.root_abs:
            return
        abs_p = os.path.abspath(path)
        real_p = os.path.realpath(abs_p)
        if not _inside(real_p, self.root_real):
            raise BoundaryError(
                "目标越出项目边界（真实位置 %s 不在 %s 内）" % (real_p, self.root_real))
        prev = self.baseline.get(abs_p)
        if prev is not None and prev != real_p:
            raise BoundaryError(
                "预检后目标真实位置发生变化（预检 %s → 现在 %s），疑似被替换" % (prev, real_p))
        rel = os.path.relpath(abs_p, self.root_abs)
        if rel.startswith(".."):
            raise BoundaryError("目标不在项目目录内: %s" % abs_p)
        cur = self.root_abs
        for part in rel.split(os.sep)[:-1]:
            cur = os.path.join(cur, part)
            if not os.path.exists(cur):
                continue
            # R4-N2：父目录（含本次新建的目录）真实位置与登记不符 ⇒ 被替换（含指向项目内的 Junction）
            bprev = self.baseline.get(os.path.abspath(cur))
            if bprev is not None and os.path.realpath(cur) != bprev:
                raise BoundaryError(
                    "父路径 %s 真实位置已变化（%s → %s），疑似被替换" % (cur, bprev, os.path.realpath(cur)))
            if _is_reparse_point(cur):
                sub_real = os.path.realpath(cur)
                if not _inside(sub_real, self.root_real):
                    raise BoundaryError(
                        "父路径 %s 是重解析点且指向项目外（%s）" % (cur, sub_real))

    # ---------------------------------------------------------- 目录
    def mkdir(self, path: str) -> None:
        """递归创建目录，并记录本进程新建的层级（用于回滚时清理）。"""
        self.guard(path)
        if os.path.isdir(path):
            return
        missing = []
        cur = os.path.abspath(path)
        while not os.path.isdir(cur):
            missing.append(cur)
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        os.makedirs(path, exist_ok=True)
        self.created_dirs.extend(missing)
        # R4-N2：新建目录登记真实位置，之后被换成 Junction/链接（即使指向项目内）也能被 guard 识别
        for d in missing:
            self.baseline.setdefault(os.path.abspath(d), os.path.realpath(d))

    # ---------------------------------------------------------- 写入
    def write(self, path: str, data: bytes, step: str = "") -> None:
        self.guard(path)
        existed = os.path.exists(path)
        original = None
        if existed:
            try:
                original = _read_raw(path)
            except OSError as exc:
                raise OSError(
                    "无法读取目标文件，拒绝在缺少恢复记录的情况下写入: %s (%s)" % (path, exc))
        entry = {"path": path, "existed": existed, "original": original,
                 "written": data, "step": step or self.step, "state": "pending"}
        self.entries.append(entry)      # 先登记意图：此后任何失败都在回滚范围内（R2-N1）
        try:
            _atomic_write(path, data)
            entry["state"] = "written"
        except BaseException as exc:
            self._compensate(entry, exc)
            raise

    def _compensate(self, entry: dict, exc: BaseException) -> None:
        """单条写入失败后就地收敛：能还原就还原，不能就如实登记残留。"""
        path = entry["path"]
        try:
            now = _read_raw(path) if os.path.exists(path) else None
        except OSError:
            now = "<unreadable>"
        if now == entry["original"]:
            entry["state"] = "aborted"          # 目标未被改动（原子写失败时的常态）
            return
        # R3-N1：补偿本身也是"改动目标"，写回 / 删除之前必须重新核对边界。
        # 写入失败到补偿执行之间，该路径的父级可能在某一刻被换成指向项目外的
        # Junction / 符号链接；若跟随过去作还原，就会把项目外的同名用户数据
        # 覆盖成项目内原内容、或直接删掉。此处做不到消除 TOCTOU（guard 与随后的
        # 写盘之间仍有极短窗口），只是让"补偿"与"首次写入"受同一套边界约束，
        # 并把无法还原的情况落到 ResidualRisk 上而不是静默放过。
        try:
            self.guard(path)
        except BoundaryError as bexc:
            entry["state"] = "residual"
            self.residuals.append({
                "path": path,
                "reason": "写入失败后自动还原前边界校验未通过，已停止还原（该路径本次未改动）："
                          "%s（原始失败 %s: %s）" % (bexc, type(exc).__name__, exc),
                "actual": _describe(path),
            })
            return
        # R4-N2：归属判据——只有当前内容仍是本进程写入值时才还原/删除；否则可能是他人内容，保留并如实报告
        if now != entry["written"]:
            entry["state"] = "residual"
            self.residuals.append({
                "path": path,
                "reason": "写入失败后当前内容既不是写入前原值也不是本进程写入值（可能被其他进程改动），"
                          "未还原、未删除（原始失败 %s: %s）" % (type(exc).__name__, exc),
                "actual": _describe(path),
            })
            return
        try:
            if entry["existed"]:
                _atomic_write(path, entry["original"])
                entry["state"] = "restored_after_failure"
            else:
                os.remove(path)
                entry["state"] = "removed_after_failure"
        except OSError as exc2:
            entry["state"] = "residual"
            self.residuals.append({
                "path": path,
                "reason": "写入失败后自动还原也失败：%s（原始失败 %s: %s）"
                          % (exc2, type(exc).__name__, exc),
                "actual": _describe(path),
            })

    # ---------------------------------------------------------- 回滚
    def rollback(self) -> list[str]:
        actions: list[str] = []
        for e in reversed(self.entries):
            path = e["path"]
            try:
                self.guard(path)
            except BoundaryError as exc:
                actions.append("Skipped(out-of-boundary) %s (%s)" % (path, exc))
                if e.get("state") != "residual":   # R4-N2：未回滚的条目必须进残留，禁止宣称"已回滚"
                    self.residuals.append({"path": path, "reason": "回滚前边界校验未通过，未回滚：%s" % exc,
                                           "actual": "未检查（不跟随被替换的路径）"})
                continue
            try:
                cur = _read_raw(path) if os.path.exists(path) else None
            except OSError as exc:          # 读不回就不动它
                actions.append("Skipped(unreadable) %s (%s)" % (path, exc))
                self.residuals.append({"path": path, "reason": "回滚时不可读，未回滚：%s" % exc,
                                       "actual": "不可读"})
                continue
            if cur == e["original"]:
                actions.append("Unchanged %s" % path)      # 本来就没改动（含写入已中止）
                continue
            if cur != e["written"]:
                actions.append("Skipped(modified-by-others) %s" % path)
                if e.get("state") != "residual":
                    self.residuals.append({"path": path, "reason": "内容已被他人改动，未回滚（不覆盖他人改动）",
                                           "actual": _describe(path)})
                continue
            try:
                if e["existed"]:
                    _atomic_write(path, e["original"])
                    actions.append("Restored %s" % path)
                else:
                    os.remove(path)
                    actions.append("Removed %s" % path)
            except OSError as exc:
                actions.append("Failed %s (%s)" % (path, exc))
                self.residuals.append({
                    "path": path,
                    "reason": "回滚失败：%s" % exc,
                    "actual": _describe(path),
                })
        for d in reversed(self.created_dirs):
            try:
                self.guard(d)
            except BoundaryError as exc:
                actions.append("Skipped(out-of-boundary) %s (%s)" % (d, exc))
                continue
            try:
                os.rmdir(d)
                actions.append("RemovedDir %s" % d)
            except OSError:
                pass                       # 非空或已不存在：保留
        return actions


def preflight(project: str, plan: dict) -> list[str]:
    """写入前的可预见问题检查；返回问题列表（非空即拒绝执行，且尚未写任何文件）。"""
    problems: list[str] = []
    if not os.path.isdir(project):
        return ["项目目录不存在或不是目录: %s" % project]
    root = os.path.realpath(project)

    def inside(p: str) -> bool:
        rp = os.path.realpath(p)
        return rp == root or rp.startswith(root + os.sep)

    targets = ["AGENTS.md", ".vibecoding", ".vibecoding/config.json",
               ".vibecoding/AGENTS.block.md", ".vibecoding/evidence",
               ".vibecoding/evidence/_template.md", ".vibecoding/HANDOFF.md"]
    for rel in targets:
        p = os.path.join(project, rel)
        if not inside(p):
            problems.append("目标路径越出项目目录（拒绝写入）: %s" % p)

    vb = os.path.join(project, ".vibecoding")
    ev = os.path.join(project, ".vibecoding", "evidence")
    agents = os.path.join(project, "AGENTS.md")
    if plan.get("status") == "conflict":
        problems.append(plan.get("detail") or "AGENTS.md 目标类型冲突")
    if os.path.exists(vb) and not os.path.isdir(vb):
        problems.append(".vibecoding 已存在但不是目录: %s" % vb)
    if os.path.exists(ev) and not os.path.isdir(ev):
        problems.append(".vibecoding/evidence 已存在但不是目录: %s" % ev)
    if plan.get("status") != "created" and os.path.isdir(agents) and plan.get("status") != "conflict":
        problems.append("AGENTS.md 是目录，无法作为文件写入: %s" % agents)
    if not os.access(project, os.W_OK):
        problems.append("项目目录不可写: %s" % project)
    return problems


def find_standard(project: str, explicit: str | None) -> tuple[str | None, str]:
    """定位标准副本目录（含 tools/verify_manifest.py 的目录）。返回 (路径, 来源说明)。"""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates: list[tuple[str, str]] = []
    if explicit:
        # 显式指定即唯一来源：路径无效时如实拒绝，不得静默回退到其他副本（P1-CLI 技能缺失如实报告）
        if os.path.isfile(os.path.join(explicit, "tools", "verify_manifest.py")):
            return os.path.abspath(explicit), "--standard 参数"
        return None, "--standard 指定的路径不存在或不是有效标准副本（未回退到其他副本）: %s" % explicit
    env = os.environ.get("VB_STANDARD_HOME")
    if env:
        candidates.append((env, "环境变量 VB_STANDARD_HOME"))
    candidates.append((os.path.normpath(os.path.join(here, "..", "vendor", "vibecoding-standard")), "技能内置 vendor"))
    project_vendor = os.path.join(project, ".vibecoding", "vendor", "vibecoding-standard")
    candidates.append((project_vendor, "项目内 .vibecoding/vendor"))

    for path, source in candidates:
        if path and os.path.isfile(os.path.join(path, "tools", "verify_manifest.py")):
            return os.path.abspath(path), source
    return None, "未找到（检查 --standard / VB_STANDARD_HOME / vendor 目录）"


def verify_vendor_access(standard: str) -> list[str]:
    """校验权威 vendor 的实际路径、文件存在性与可读性（F-2）。

    返回问题列表；非空即视为「接入缺失」——拒绝初始化，而不是写一个指向空路径的注入块。
    """
    problems: list[str] = []
    if not os.path.isdir(standard):
        return ["vendor 路径不是目录: %s" % standard]
    doc = os.path.join(standard, "AI_PROJECT_STANDARD.md")
    if not os.path.isfile(doc):
        problems.append("缺少规范正文 AI_PROJECT_STANDARD.md: %s" % doc)
    else:
        try:
            with open(doc, "rb") as fh:
                head = fh.read(1)
            if not head:
                problems.append("规范正文为空文件: %s" % doc)
        except OSError as exc:
            problems.append("规范正文不可读: %s (%s)" % (doc, exc))
    if not os.path.isfile(os.path.join(standard, "MANIFEST.sha256")):
        problems.append("缺少 MANIFEST.sha256（无法证明与签收版本一致）: %s" % standard)
    if not os.path.isfile(os.path.join(standard, "tools", "verify_manifest.py")):
        problems.append("缺少 tools/verify_manifest.py（无法自校验）: %s" % standard)
    return problems


def vendor_reference(project: str, standard: str) -> dict:
    """把已定位的 vendor 转成「可写进项目文件 + 可被 Agent 解析」的引用（F-2）。

    - 在项目内 → 写项目相对路径（随项目整体移动仍有效）。
    - 在项目外 → 写绝对路径，并如实标注其与本机安装位置绑定、换机器或移动技能后失效。
    **不复制整份规范进项目**（只引用，不产生第二份规则副本）。
    """
    root = os.path.realpath(project)
    real = os.path.realpath(standard)
    if _inside(real, root):
        rel = os.path.relpath(real, root).replace("\\", "/")
        return {
            "path": rel,
            "kind": "project_relative",
            "inside_project": True,
            "condition": "项目内相对路径，随项目整体移动仍有效；技能被卸载则该路径消失",
        }
    return {
        "path": os.path.abspath(standard).replace("\\", "/"),
        "kind": "absolute_external",
        "inside_project": False,
        "condition": "项目外绝对路径，与本机技能安装位置绑定；换机器或移动技能后失效，需重新 --apply 重定位",
    }


def verify_standard(standard: str, python_exe: str) -> tuple[int, list[str]]:
    rc, out, err = run([python_exe, os.path.join(standard, "tools", "verify_manifest.py")], cwd=standard, timeout=300)
    tail = [l for l in (out + err).strip().splitlines() if l.strip()][-6:]
    return rc, tail


def split_block(text: str) -> tuple[int, int] | None:
    """返回标记块的 (start, end) 字节偏移（字符索引），无块返回 None。"""
    i = text.find(BEGIN)
    if i < 0:
        return None
    j = text.find(END, i)
    if j < 0:
        return None
    return i, j + len(END)


def normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def plan_agents(project: str, desired_block: str) -> dict:
    path = os.path.join(project, "AGENTS.md")
    if not os.path.exists(path):
        return {"file": "AGENTS.md", "status": "created", "detail": "不存在，将创建并写入标记块", "path": path}
    if os.path.isdir(path):
        return {"file": "AGENTS.md", "status": "conflict",
                "detail": "AGENTS.md 是目录，无法作为文件读写: %s" % path, "path": path}
    raw = _read_raw(path)
    text = raw.decode("utf-8", "replace")
    span = split_block(text)
    if span is None:
        return {"file": "AGENTS.md", "status": "appended", "detail": "存在且无标记块，将在文件末尾追加（原有内容不动）", "path": path}
    existing = text[span[0]:span[1]]
    if normalize(existing) == normalize(desired_block):
        return {"file": "AGENTS.md", "status": "unchanged", "detail": "标记块已存在且一致（幂等）", "path": path}
    return {"file": "AGENTS.md", "status": "differs", "detail": "标记块存在但内容不同，需 --update-block 才更新", "path": path}


def apply_agents(plan: dict, desired_block: str, update_block: bool, project: str,
                 journal: WriteJournal) -> str:
    path = plan["path"]
    if plan["status"] in ("unchanged", "differs"):
        if plan["status"] == "differs":
            if not update_block:
                return "skipped(需 --update-block)"
            raw = _read_raw(path)
            text = raw.decode("utf-8", "replace")
            span = split_block(text)
            eol = "\r\n" if detect_eol(path) == b"\r\n" else "\n"
            new = text[:span[0]] + desired_block.replace("\n", eol).rstrip("\r\n") + text[span[1]:]
            journal.write(path, new.encode("utf-8"), step="AGENTS.md 更新标记块")
            return "block_updated"
        return "no_change"

    eol_bytes = detect_eol(path) if os.path.exists(path) else b"\n"
    block_bytes = desired_block.replace("\n", eol_bytes.decode()).rstrip("\r\n").encode("utf-8")

    if plan["status"] == "created":
        journal.write(path, block_bytes + eol_bytes, step="AGENTS.md 创建")
        return "created"

    existing = _read_raw(path)
    payload = bytearray(existing)
    if existing and not existing.endswith(b"\n"):
        payload += eol_bytes
    payload += eol_bytes
    payload += block_bytes
    payload += eol_bytes
    journal.write(path, bytes(payload), step="AGENTS.md 追加标记块")
    return "appended"


def write_if_changed(path: str, content: bytes, journal: WriteJournal | None = None) -> str:
    if os.path.exists(path):
        if _read_raw(path) == content:
            return "unchanged"
        return "differs"
    if journal is not None:
        journal.mkdir(os.path.dirname(path))
        journal.write(path, content, step="写入 %s" % os.path.basename(path))
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _write_raw(path, content)
    return "created"


def print_residuals(residuals: list[dict]) -> bool:
    """打印残留风险；返回是否存在残留（存在时上层禁止宣称"已全部回滚"）。"""
    if not residuals:
        return False
    print("--- 残留风险（ResidualRisk）---")
    for r in residuals:
        print("  ResidualRisk %s" % r["path"])
        print("      原因     : %s" % r["reason"])
        print("      实际残留 : %s" % r["actual"])
    print("  说明: 上述路径未能还原为写入前状态，请人工核对后再使用该项目。")
    return True


def _main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Vibecoding Skill 受保护初始化（默认 dry-run）")
    ap.add_argument("--project", default=".", help="目标项目目录（默认当前目录）")
    ap.add_argument("--standard", help="标准副本目录（含 tools/verify_manifest.py）")
    ap.add_argument("--apply", action="store_true", help="实际落盘；缺省为 dry-run")
    ap.add_argument("--allow-dirty", action="store_true", help="工作区脏时仍允许改 tracked 文件")
    ap.add_argument("--update-block", action="store_true", help="标记块内容不同时允许覆盖")
    ap.add_argument("--skip-standard-check", action="store_true", help="跳过标准副本完整性校验（不推荐）")
    ap.add_argument("--python", default=sys.executable, help="用于调用标准工具的解释器")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = ap.parse_args(argv)

    project = os.path.abspath(args.project)
    if not os.path.isdir(project):
        print("ERROR: 项目目录不存在: %s" % project)
        return 1

    result: dict = {"project": project, "mode": "apply" if args.apply else "dry-run", "steps": [], "rc": 0}

    standard, source = find_standard(project, args.standard)
    if not standard:
        print("REFUSED: 未找到标准副本（接入缺失）。%s" % source)
        print("  接入缺失的含义：本技能不带第二份规范副本，规范正文必须来自已安装技能的 vendor。")
        print("  处置：重新安装技能（或安装到项目内 <项目>/.claude/skills/vibecoding），再执行一次 --apply。")
        return 1
    result["standard"] = {"path": standard, "source": source}

    access = verify_vendor_access(standard)
    if access:
        print("REFUSED: 规范接入缺失（未写入任何文件）。")
        for p in access:
            print("  - " + p)
        print("  不写指向空路径的注入块：那会让后续会话误以为规范已加载。")
        return 1
    vref = vendor_reference(project, standard)
    result["standard"]["vendor_ref"] = vref

    if not args.skip_standard_check:
        rc, tail = verify_standard(standard, args.python)
        result["standard"]["verify_rc"] = rc
        result["standard"]["verify_tail"] = tail
        if rc != 0:
            print("REFUSED: 标准副本完整性校验未通过（退出码 %d），未写入任何文件。" % rc)
            for line in tail:
                print("  " + line)
            return 1
    else:
        result["standard"]["verify_rc"] = None
        result["standard"]["verify_tail"] = ["skipped"]

    state = git_state(project)
    result["git"] = {k: state[k] for k in ("is_repo", "root", "head", "branch", "dirty")}

    desired_block = BLOCK.format(sv=SKILL_VERSION, std=STANDARD_VERSION,
                                 vendor_path=vref["path"], vendor_condition=vref["condition"])
    plan = plan_agents(project, desired_block)

    touch_tracked = plan["status"] in ("appended", "differs") or (plan["status"] == "created" and state["is_repo"])
    if args.apply and state["dirty"] and touch_tracked and not args.allow_dirty:
        print("REFUSED: 工作区有未提交改动，且本次会修改 AGENTS.md。确认无冲突后加 --allow-dirty。")
        print(state["porcelain"] or "(status 为空但 dirty 判定为真)")
        return 1

    # 预检前的真实位置基线：写入时若与它不一致 ⇒ 目标在预检后被替换（R2-N2）
    baseline: dict[str, str] = {}
    for _rel in ("", ".vibecoding", ".vibecoding/evidence", "AGENTS.md"):
        _p = os.path.join(project, _rel) if _rel else project
        if os.path.exists(_p):
            baseline[os.path.abspath(_p)] = os.path.realpath(_p)

    journal = WriteJournal(root=project, baseline=baseline)
    state_cfg = "would_write"
    state_block = "would_write"
    state_ev = "would_write"
    state_ho = "exists(unchanged)" if os.path.exists(os.path.join(project, ".vibecoding", "HANDOFF.md")) else "would_create"

    if not args.apply:
        plan["action"] = "would_" + plan["status"]
        result["steps"].append(plan)
        result["steps"].append({"file": ".vibecoding/config.json", "status": state_cfg})
        result["steps"].append({"file": ".vibecoding/AGENTS.block.md", "status": state_block})
        result["steps"].append({"file": ".vibecoding/evidence/_template.md", "status": state_ev})
        result["steps"].append({"file": ".vibecoding/HANDOFF.md", "status": state_ho})
    else:
        problems = preflight(project, plan)
        if problems:
            print("REFUSED: 写入前检查未通过（未写入任何文件）。")
            for p in problems:
                print("  - " + p)
            return 1

        # 规范位置：项目内用相对路径（随项目移动有效），项目外用绝对路径（并已标注失效条件）。
        # 不再使用 os.path.relpath 生成"越出项目"的 ../../ 相对路径（R2 的 F-2 事实之一）。
        vendor_rel = vref["path"]

        manifest = {
            "skill_version": SKILL_VERSION,
            "standard_version": STANDARD_VERSION,
            "standard_signoff_commit": STANDARD_SIGNOFF,
            "standard_release_commit": STANDARD_RELEASE,
            "standard_vendor_zip_sha256": STANDARD_ZIP_SHA,
            "standard_vendor_path": vendor_rel,
            "initialized_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        }
        cfg_path = os.path.join(project, ".vibecoding", "config.json")
        try:
            # 1) 先建目录：这是 F-1 的根因修复点（原先直接写 config.json 导致 FileNotFoundError）
            journal.step = "创建 .vibecoding/ 目录"
            journal.mkdir(os.path.join(project, ".vibecoding"))
            journal.mkdir(os.path.join(project, ".vibecoding", "evidence"))

            # 2) config.json（幂等：只比稳定字段，initialized_at 保留原值）
            journal.step = ".vibecoding/config.json"
            stable = ("skill_version", "standard_version", "standard_signoff_commit",
                      "standard_release_commit", "standard_vendor_zip_sha256", "standard_vendor_path")
            prev = None
            if os.path.exists(cfg_path):
                try:
                    prev = json.loads(_read_raw(cfg_path).decode("utf-8"))
                except (json.JSONDecodeError, OSError):
                    prev = None
            cfg_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if prev is not None and all(prev.get(k) == manifest.get(k) for k in stable):
                state_cfg = "unchanged"
            elif prev is not None:
                manifest["initialized_at"] = prev.get("initialized_at") or manifest["initialized_at"]
                cfg_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                journal.write(cfg_path, cfg_bytes, step=".vibecoding/config.json 更新")
                state_cfg = "updated"
            else:
                journal.write(cfg_path, cfg_bytes, step=".vibecoding/config.json 创建")
                state_cfg = "created"

            # 3) AGENTS.block.md 副本（存在且不同则不动，保持原语义）
            journal.step = ".vibecoding/AGENTS.block.md"
            state_block = write_if_changed(os.path.join(project, ".vibecoding", "AGENTS.block.md"),
                                           desired_block.encode("utf-8"), journal)

            # 4) evidence/_template.md
            journal.step = ".vibecoding/evidence/_template.md"
            state_ev = write_if_changed(
                os.path.join(project, ".vibecoding", "evidence", "_template.md"),
                EVIDENCE_TEMPLATE.format(sv=SKILL_VERSION, task="<TASK-ID>", ts="<日期 时间 时区>",
                                         baseline="<commit>", env="<系统 / 运行时>").encode("utf-8"),
                journal)

            # 5) HANDOFF.md（仅在不存在时创建）
            journal.step = ".vibecoding/HANDOFF.md"
            handoff = os.path.join(project, ".vibecoding", "HANDOFF.md")
            if not os.path.exists(handoff):
                ws = "%s @ %s" % (state["branch"], state["head"][:12]) if state["is_repo"] else project
                baseline = state["head"] if state["is_repo"] else "无版本基线"
                journal.write(handoff, HANDOFF_TEMPLATE.format(
                    sv=SKILL_VERSION,
                    task="<TASK-ID>",
                    ts=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
                    workspace=ws,
                    baseline=baseline,
                    summary="（待填写）",
                    verify="（待填写）",
                    blocked="（待填写）",
                    effects="无",
                    hygiene="无",
                    next="（待填写）",
                ).encode("utf-8"), step=".vibecoding/HANDOFF.md 创建")
                state_ho = "created"

            # 6) 最后才动用户的 tracked 文件，缩短"已改用户文件"的时间窗
            journal.step = "AGENTS.md"
            plan["action"] = apply_agents(plan, desired_block, args.update_block, project, journal)
        except BoundaryError as exc:      # R2-N2：越界或目标被替换，停止初始化
            actions = journal.rollback()
            print("REFUSED: 检测到越界写入风险，已停止初始化（未继续其余步骤）。")
            print("  原因     : %s" % exc)
            print("  说明     : 预检与写入之间目标真实位置发生变化，可能是符号链接 / Junction / 其他重解析点。")
            print("             这不能证明操作恶意，但无法保证写入落在项目内，故拒绝继续。")
            print("--- 回滚动作 ---")
            for a in actions:
                print("  " + a)
            print_residuals(journal.residuals)
            print("== 结论: REFUSED（边界风险，退出码 1）==")
            return 1
        except Exception as exc:  # 可控异常：回滚本次写入，不删除用户原有文件
            actions = journal.rollback()
            has_residual = bool(journal.residuals)
            # 有残留时不得用完成式措辞，只能说"已尝试"（R2-N1 第 5 条）
            print("ERROR: 初始化失败，%s。" % (
                "已尝试按逆序回滚本次写入（存在未还原项）" if has_residual
                else "已按逆序回滚本次写入"))
            print("  失败步骤 : %s" % journal.step)
            print("  异常类型 : %s" % type(exc).__name__)
            print("  异常信息 : %s" % exc)
            print("--- 回滚动作 ---")
            for a in actions:
                print("  " + a)
            if print_residuals(journal.residuals):
                print("== 结论: FAILED（回滚不完整，存在残留，退出码 1）==")
            else:
                print("== 结论: FAILED（已回滚，退出码 1）==")
            return 1

        result["steps"].append(plan)
        result["steps"].append({"file": ".vibecoding/config.json", "status": state_cfg})
        result["steps"].append({"file": ".vibecoding/AGENTS.block.md", "status": state_block})
        result["steps"].append({"file": ".vibecoding/evidence/_template.md", "status": state_ev})
        result["steps"].append({"file": ".vibecoding/HANDOFF.md", "status": state_ho})

    claude_md = os.path.join(project, "CLAUDE.md")
    if os.path.exists(claude_md):
        result["manual_required"] = [
            "检测到 CLAUDE.md：本脚本不会编辑它。",
            "Claude Code 默认仅在工作目录及其上方都没有 CLAUDE.md 类文件时才读 AGENTS.md。",
            "解法一：Project instructions 设为 claude-md-and-agents-md。",
            "解法二：在 CLAUDE.md 首行加入 @AGENTS.md。",
        ]
    # 退出码反映**操作完成后**的真实状态（F-5）：
    # - 块 differs 且未获 --update-block 授权 → 仍有待决事项 → 2
    # - 块已按授权更新（block_updated）→ 待决事项已消解 → 0
    # - 其他未解决问题（拒绝/异常）在上面各分支已返回非零，不会走到这里
    action = plan.get("action", "")
    needs_decision = (plan["status"] == "differs") and (action != "block_updated")
    result["rc"] = 2 if needs_decision else 0
    result["needs_decision"] = needs_decision
    result["block_updated"] = (action == "block_updated")

    if args.json:
        result["status"] = "needs_decision" if result["rc"] == 2 else "ok"
        _JSON_RESULT.append(result)
    else:
        print("== Vibecoding 初始化（%s）==" % result["mode"])
        print("项目      : %s" % project)
        print("标准来源  : %s" % source)
        print("标准副本  : %s" % standard)
        print("规范定位  : %s（%s）" % (vref["path"], vref["condition"]))
        print("标准校验  : rc=%s %s" % (result["standard"]["verify_rc"], "PASS" if result["standard"]["verify_rc"] == 0 else "见下"))
        for line in result["standard"]["verify_tail"]:
            print("            " + line)
        print("Git       : %s" % ("repo=%s branch=%s head=%s dirty=%s" % (state["is_repo"], state["branch"], (state["head"] or "")[:12], state["dirty"]) if state["is_repo"] else "非 Git 仓库"))
        print("--- 步骤 ---")
        for step in result["steps"]:
            print("  %-34s %-18s %s" % (step.get("file"), step.get("status"), step.get("action", "")))
        if result.get("manual_required"):
            print("--- 需人工处理 ---")
            for line in result["manual_required"]:
                print("  " + line)
        if result["rc"] == 2:
            verdict = "NEED_DECISION（标记块 differs，未获 --update-block 授权）"
        elif result["block_updated"]:
            verdict = "OK（标记块已更新）"
        else:
            verdict = "OK"
        print("== 结论: %s ==" % verdict)
    return result["rc"]

# ------------------------------------------------ --json 输出契约（P1-CLI-1）
# 成功路径：输出 result（含 status=ok|needs_decision、rc、steps …）。
# 任何非成功路径（拒绝 / 失败 / 参数错误 / 未预期异常）：也只输出一个 JSON 对象，
#   {"status": "refused"|"failed"|"usage_error", "rc": <与进程退出码相同>, "error": <首条说明>,
#    "messages": [<原散文逐行>], "mode", "project", "steps": [], "needs_decision": false, "block_updated": false}
# stdout 上不再出现 JSON 以外的散文。
_JSON_RESULT: list = []


def main(argv: list[str]) -> int:
    if "--json" not in argv:
        return _main(argv)
    del _JSON_RESULT[:]
    buf = io.StringIO()
    usage_error = False
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = _main(argv)
    except SystemExit as exc:  # argparse 用法错误
        rc = exc.code if isinstance(exc.code, int) else 2
        usage_error = True
    except Exception as exc:  # noqa: BLE001 — JSON 模式下也要给出契约内的失败结果
        buf.write("ERROR: 未预期异常 %s: %s\n" % (type(exc).__name__, exc))
        rc = 1
    lines = [l.rstrip() for l in buf.getvalue().splitlines() if l.strip()]
    if _JSON_RESULT and _JSON_RESULT[-1].get("rc") == rc and not usage_error:
        payload = _JSON_RESULT[-1]
        if lines:
            payload["messages"] = lines
    else:
        first = lines[0] if lines else ""
        status = "usage_error" if usage_error else ("refused" if first.startswith("REFUSED") else "failed")
        proj = None
        if "--project" in argv and argv.index("--project") + 1 < len(argv):
            proj = os.path.abspath(argv[argv.index("--project") + 1])
        payload = {"status": status, "rc": rc, "error": first, "messages": lines,
                   "mode": "apply" if "--apply" in argv else "dry-run", "project": proj,
                   "steps": [], "needs_decision": False, "block_updated": False}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
