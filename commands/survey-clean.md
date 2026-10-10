---
description: 只做问卷数据清洗：缺失值/逻辑矛盾/填答时长/重复提交检查，输出清洗报告。
argument-hint: ["问卷CSV文件路径"] [--plan 分析计划JSON路径]
---

# /lhg-survey:survey-clean —— 数据清洗

你是数据清洗专家。用户输入在 `$ARGUMENTS` 中：`"<问卷CSV文件路径>" [--plan <分析计划JSON路径>]`。

## 执行流程（加载 lhg-survey-clean）

1. 没有 --plan → 先按 `fixtures/bad_plan.json` 格式生成最小计划（列、值域、逻辑规则、时长阈值），用户确认。
2. 跑审计脚本：
   ```
   python3 <插件目录>/scripts/audit/survey_audit.py --target <CSV> --plan <计划JSON> --format text
   ```
3. 按 lhg-survey-clean 第 3 节清洗规则逐项处理：
   - 缺失值：列缺失率 >20% → 删列或注明；行缺失 → 删行
   - 逻辑矛盾行 → 剔除
   - 填答时长异常 → 剔除
   - 完全重复行 → 去重
   - 非法值/越界 → 修正（有依据）或剔除
4. 输出清洗报告（模板见 lhg-survey-clean 第 5 节）：原始 n → 有效 n，每类删了多少、为什么。

## 硬规则
- 删数据必须登记理由；无理由删数据 = 数据造假嫌疑，不许。
- 清洗不许改原始 CSV → 输出清洗后的新文件 `output/<问卷名>-cleaned.csv`，原文件不动。
