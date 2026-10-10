#!/usr/bin/env python3
"""lhg-survey 问卷数据确定性审计脚本。

输入：一份问卷 CSV + 一份分析计划 JSON（见 fixtures/*_plan.json 示例）。
检查：
  SV-CSV-001   blocker  文件无法读取/无数据行
  SV-CSV-002   warning  某些行列数与表头不一致
  SV-COL-001   blocker  计划要求的列缺失
  SV-NULL-001  warning  某列缺失值率超阈值
  SV-DUP-001   warning  完全重复行占比超阈值
  SV-VAL-001   warning  枚举列出现非法值 / 数值列越界
  SV-LOGIC-001 warning  逻辑矛盾行（如 未成年人已婚）
  SV-TIME-001  warning  填答时长异常（低于最小时长）
  SV-STAT-001  warning  统计方法误用拦截（t检验/卡方/相关的适用条件）
  SV-CHART-001 warning  图表引用了 CSV 不存在的列
  SV-NUM-001   warning  报告摘要数字与 CSV 实际对不上

用法：
  python3 survey_audit.py --target <数据.csv> --plan <分析计划.json> --format json|text
退出码：0=无 blocker（只有 warning 也通过），1=有 blocker，2=用法/读取错误。

纯标准库，零第三方依赖。
"""

import argparse
import ast
import csv
import json
import sys
from collections import Counter


# ---------------- 基础工具 ----------------

def _read_csv(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
    except Exception:
        return None
    return rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_missing(v):
    return v is None or str(v).strip() == ""


# ---------------- 逻辑表达式安全求值 ----------------

_ALLOWED = (ast.Expression, ast.BoolOp, ast.Compare, ast.Name, ast.Constant,
            ast.UnaryOp, ast.And, ast.Or, ast.Not, ast.USub,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
            ast.Load, ast.Store, ast.Del)  # 变量上下文节点


def _safe_eval(expr, row):
    """只允许 Name/Compare/BoolOp/常量 的子集求值；出错返回 False。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            return False

    def val(node):
        if isinstance(node, ast.Name):
            raw = row.get(node.id, "")
            n = _num(raw)
            return n if n is not None else str(raw)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp):
            v = val(node.operand)
            if isinstance(node.op, ast.Not):
                return not v
            if isinstance(node.op, ast.USub):
                return -v
            raise ValueError("bad unary")
        raise ValueError("bad node")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.BoolOp):
            vals = [ev(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not ev(node.operand)
        if isinstance(node, ast.Compare):
            left = val(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = val(comp)
                try:
                    if isinstance(op, ast.Eq):
                        ok = left == right
                    elif isinstance(op, ast.NotEq):
                        ok = left != right
                    elif isinstance(op, ast.Lt):
                        ok = left < right
                    elif isinstance(op, ast.LtE):
                        ok = left <= right
                    elif isinstance(op, ast.Gt):
                        ok = left > right
                    elif isinstance(op, ast.GtE):
                        ok = left >= right
                    else:
                        return False
                except TypeError:
                    return False
                if not ok:
                    return False
                left = right
            return True
        return bool(val(node))

    try:
        return bool(ev(tree))
    except Exception:
        return False


# ---------------- 审计 ----------------

def audit(rows, plan):
    findings = []

    def add(rule_id, severity, title, line=0, detail=""):
        findings.append({"rule_id": rule_id, "severity": severity,
                         "title": title, "line": line, "detail": detail})

    if not rows or len(rows) < 2:
        add("SV-CSV-001", "blocker", "CSV 无数据行",
            detail="文件为空或只有表头，没有可分析的数据。")
        return _wrap(findings)

    header = [h.strip() for h in rows[0]]
    data_rows = rows[1:]
    ncol = len(header)

    # SV-CSV-002：列数不一致
    bad_shape = [i + 2 for i, r in enumerate(data_rows) if len(r) != ncol]
    if bad_shape:
        add("SV-CSV-002", "warning",
            "有 %d 行列数与表头不一致（第%s行）" % (len(bad_shape), bad_shape[:5]),
            detail="列数对不上的行会被剔除出有效样本。检查是否串行/多分隔符。")
    good_rows = [(i + 2, r) for i, r in enumerate(data_rows) if len(r) == ncol]
    dicts = [{h: r[j].strip() for j, h in enumerate(header)} for _, r in good_rows]
    effective_n = len(good_rows)

    # SV-COL-001：缺列（blocker）
    expected = plan.get("expected_columns", [])
    missing_cols = [c for c in expected if c not in header]
    if missing_cols:
        add("SV-COL-001", "blocker", "计划要求的列缺失：%s" % "、".join(missing_cols),
            detail="分析计划里声明了这些列，但 CSV 里没有。先补数据或修正计划。")

    miss_thr = float(plan.get("missing_threshold", 0.2))
    # SV-NULL-001：缺失值率
    for col in header:
        vals = [d[col] for d in dicts]
        rate = sum(1 for v in vals if _is_missing(v)) / len(vals) if vals else 0
        if rate > miss_thr:
            add("SV-NULL-001", "warning",
                "列「%s」缺失值率 %.1f%%，超过阈值 %.0f%%" % (col, rate * 100, miss_thr * 100),
                detail="缺失太多会让统计结论失真。决定：删除该列 / 插补并注明 / 回收更多样本。")

    # SV-DUP-001：完全重复行
    dup_thr = float(plan.get("duplicate_threshold", 0.05))
    counts = Counter(tuple(d[h] for h in header) for d in dicts)
    dup_n = sum(c - 1 for c in counts.values() if c > 1)
    if dicts and dup_n / len(dicts) > dup_thr:
        add("SV-DUP-001", "warning",
            "完全重复行 %d 行（占比 %.1f%%），超过阈值 %.0f%%" % (dup_n, dup_n / len(dicts) * 100, dup_thr * 100),
            detail="重复可能是重复提交。建议去重并注明去重规则，重复率异常高时要怀疑数据造假。")

    # SV-VAL-001：非法值/越界
    for col, allowed in plan.get("value_sets", {}).items():
        if col not in header:
            continue
        bad = [(ln, d[col]) for ln, d in zip([ln for ln, _ in good_rows], dicts)
               if not _is_missing(d[col]) and d[col] not in allowed]
        if bad:
            add("SV-VAL-001", "warning",
                "列「%s」有 %d 个非法值（如第%d行「%s」，允许值：%s）"
                % (col, len(bad), bad[0][0], bad[0][1], "/".join(allowed[:6])),
                line=bad[0][0],
                detail="非法值可能是录入错误或问卷逻辑漏洞。修正或剔除，并在清洗报告里登记。")
    for col, (lo, hi) in plan.get("numeric_ranges", {}).items():
        if col not in header:
            continue
        bad = []
        for ln, d in zip([ln for ln, _ in good_rows], dicts):
            if _is_missing(d[col]):
                continue
            n = _num(d[col])
            if n is None or not (lo <= n <= hi):
                bad.append((ln, d[col]))
        if bad:
            add("SV-VAL-001", "warning",
                "列「%s」有 %d 个越界/非数值（如第%d行「%s」，允许范围 %s~%s）"
                % (col, len(bad), bad[0][0], bad[0][1], lo, hi),
                line=bad[0][0],
                detail="年龄 200 岁这种值会直接污染均值。核对原始问卷，修正或剔除。")

    # SV-LOGIC-001：逻辑矛盾
    for rule in plan.get("logic_rules", []):
        name, expr = rule.get("name", "未命名"), rule.get("expr", "")
        hit = [ln for ln, d in zip([ln for ln, _ in good_rows], dicts)
               if _safe_eval(expr, d)]
        if hit:
            add("SV-LOGIC-001", "warning",
                "逻辑矛盾「%s」命中 %d 行（如第%d行）" % (name, len(hit), hit[0]),
                line=hit[0],
                detail="自相矛盾的答卷说明填答不认真或问卷逻辑有漏洞。建议剔除并计入清洗报告。")

    # SV-TIME-001：填答时长异常
    dur_col = plan.get("duration_col")
    min_dur = plan.get("min_duration_sec")
    if dur_col and min_dur is not None and dur_col in header:
        bad = [(ln, d[dur_col]) for ln, d in zip([ln for ln, _ in good_rows], dicts)
               if _num(d[dur_col]) is not None and _num(d[dur_col]) < min_dur]
        if bad:
            add("SV-TIME-001", "warning",
                "填答时长异常：%d 行低于最小时长 %s 秒（如第%d行 %s 秒）"
                % (len(bad), min_dur, bad[0][0], bad[0][1]),
                line=bad[0][0],
                detail="几秒钟做完的问卷基本是乱填。建议剔除，并在问卷设计时加最短时长拦截。")

    # SV-STAT-001：统计方法误用拦截
    for st in plan.get("stats", []):
        method = st.get("method", "")
        if method == "t_test":
            gc, vc = st.get("group_col"), st.get("value_col")
            if gc not in header or vc not in header:
                continue
            groups = {}
            for d in dicts:
                if _is_missing(d[gc]) or _is_missing(d[vc]) or _num(d[vc]) is None:
                    continue
                groups.setdefault(d[gc], []).append(_num(d[vc]))
            if len(groups) != 2:
                add("SV-STAT-001", "warning",
                    "t 检验误用：分组列「%s」有 %d 组（t 检验只适用于 2 组，多组请用方差分析）" % (gc, len(groups)),
                    detail="方法选错了，p 值没有意义。按统计选择树（见 skill lhg-survey-stats）重选方法。")
            else:
                small = {g: len(v) for g, v in groups.items() if len(v) < 30}
                if small:
                    add("SV-STAT-001", "warning",
                        "t 检验误用：组样本量 <30（%s），小样本 t 检验结论不可靠"
                        % "、".join("%s:n=%d" % (g, n) for g, n in small.items()),
                        detail="样本量不够时，先扩大样本或改用非参数检验，并在报告局限里声明。")
        elif method == "chi_square":
            ca, cb = st.get("col_a"), st.get("col_b")
            if ca not in header or cb not in header:
                continue
            pairs = [(d[ca], d[cb]) for d in dicts
                     if not _is_missing(d[ca]) and not _is_missing(d[cb])]
            n = len(pairs)
            ra = Counter(p[0] for p in pairs)
            cb_ = Counter(p[1] for p in pairs)
            tab = Counter(pairs)
            bad_exp = [k for k in tab
                       if ra[k[0]] * cb_[k[1]] / n < 5] if n else []
            if n and bad_exp:
                add("SV-STAT-001", "warning",
                    "卡方检验误用：有 %d 个格子期望频数 <5（如 %s），卡方近似失效"
                    % (len(bad_exp), bad_exp[0]),
                    detail="改用 Fisher 精确检验，或合并稀疏类别后再检验。")
        elif method == "correlation":
            cx, cy = st.get("col_x"), st.get("col_y")
            if cx not in header or cy not in header:
                continue
            pairs = [(_num(d[cx]), _num(d[cy])) for d in dicts]
            pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
            non_num = sum(1 for d in dicts
                          if not _is_missing(d[cx]) and _num(d[cx]) is None) + \
                sum(1 for d in dicts
                    if not _is_missing(d[cy]) and _num(d[cy]) is None)
            if non_num:
                add("SV-STAT-001", "warning",
                    "相关分析误用：列「%s」/「%s」含非数值，Pearson 相关只适用于数值变量"
                    % (cx, cy),
                    detail="分类变量的相关用卡方或 Cramer's V，别硬算 Pearson。")
            elif len(pairs) < 30:
                add("SV-STAT-001", "warning",
                    "相关分析误用：有效样本 n=%d <30，相关系数不稳定" % len(pairs),
                    detail="小样本的相关系数看看就好，别写进结论。")

    # SV-CHART-001：图表引用的列不存在
    for ch in plan.get("charts", []):
        title = ch.get("title", "未命名图表")
        missing = [c for c in ch.get("columns", []) if c not in header]
        if missing:
            add("SV-CHART-001", "warning",
                "图表「%s」引用了 CSV 不存在的列：%s" % (title, "、".join(missing)),
                detail="图表和数据源对不上，报告里的图就是错的。修正图表配置或补列。")

    # SV-NUM-001：摘要数字与实际对不上
    for name, claimed in plan.get("summary_numbers", {}).items():
        actual = {"有效样本量": effective_n}.get(name)
        if actual is not None and actual != claimed:
            add("SV-NUM-001", "warning",
                "摘要数字对不上：「%s」报告写 %s，CSV 实际 %s" % (name, claimed, actual),
                detail="报告里的数字和数据源不一致，发布前必须对齐。这是信任红线。")

    return _wrap(findings)


def _wrap(findings):
    summary = {"blocker": 0, "warning": 0, "nit": 0}
    for f in findings:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1
    return {"findings": findings, "summary": summary}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--format", choices=["json", "text"], default="text")
    args = ap.parse_args()

    rows = _read_csv(args.target)
    if rows is None:
        print("无法读取目标文件：%s" % args.target, file=sys.stderr)
        return 2
    try:
        with open(args.plan, encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as e:
        print("无法读取分析计划：%s" % e, file=sys.stderr)
        return 2

    result = audit(rows, plan)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("lhg-survey 审计：%s" % args.target)
        print("blocker=%d warning=%d nit=%d" % (
            result["summary"]["blocker"], result["summary"]["warning"],
            result["summary"]["nit"]))
        for f in result["findings"]:
            print("[%s][%s] %s" % (f["severity"], f["rule_id"], f["title"]))
            if f["line"]:
                print("    第%d行" % f["line"])
            if f["detail"]:
                print("    %s" % f["detail"])
    return 1 if result["summary"]["blocker"] else 0


if __name__ == "__main__":
    sys.exit(main())
