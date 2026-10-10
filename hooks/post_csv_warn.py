#!/usr/bin/env python3
"""lhg-survey 硬门②：写入问卷 CSV/分析计划后提醒跑审计。

触发：PostToolUse / Write|Edit。只在写入 .csv 或 *plan*.json 时输出提醒；
其余 0 开销放行。

逃生方式：LHG_SURVEY_HOOKS_OFF=1（本次 hook 直接放行，不输出提醒）。

设计原则：只提醒、不拦截；内部出错 fail-open；零第三方依赖。
"""

import json
import os
import sys


def main() -> int:
    if os.environ.get("LHG_SURVEY_HOOKS_OFF") == "1":
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # fail-open

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    low = file_path.lower()
    if not (low.endswith(".csv") or low.endswith("plan.json")):
        return 0

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                "刚写入的看起来像问卷数据/分析计划。建议跑一遍审计再往下走：\n"
                "python3 <插件目录>/scripts/audit/survey_audit.py --target %s --plan <分析计划.json> --format text\n"
                "或 /lhg-survey:survey-audit（数据质量 + 统计误用 + 图表一致性）。blocker不清零报告不许发出。"
                % file_path
            ),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
