<!-- About 简介（推送后填写到仓库 About 栏）：
问卷分析专家：CSV问卷数据→清洗→统计→图表→结论报告一键生成 ｜ 一键安装：/plugin marketplace add lhg-plugs/lhg-survey
-->
<!-- topics（推送后打）：claude-code, claude-plugin, agent-skills, survey, questionnaire, data-analysis -->

# lhg-survey：问卷分析专家

> **一句话介绍**：给 AI 助手装上"问卷分析流水线"——CSV 问卷数据→数据清洗→描述统计→交叉分析→图表→结论报告，链路极度标准化，一键出报告。
>
> **一键安装**：在 Claude Code 里运行
> ```
> /plugin marketplace add lhg-plugs/lhg-survey
> /plugin install lhg-survey@lhg-plugs
> ```

## 它是什么

`lhg-survey` 是一个 Claude Code 插件（plugin 为主、skill 为辅）：

- **3 个命令**（小白入口）：`survey` 清洗→统计→图表→报告一条龙，`survey-clean` 只做数据清洗，`survey-audit` 分析审计
- **4 个平台中立 skill**（方法论，可移植到豆包/Workbuddy 等）：数据清洗、统计方法选择树、图表选型、结论三段式
- **3 个专家 agent**：数据清洗专家、统计分析专家、报告撰写专家
- **2 个硬门 hooks**：commit 前问卷数据审计拦截、写 CSV/分析计划提醒（均可一键豁免）
- **11 条确定性审计规则**：纯 Python、零第三方依赖，查数据质量（缺失/重复/矛盾/时长）+ 统计误用拦截（t 检验/卡方/相关适用条件）+ 图表数据一致性

差异化：**链路极度标准化**（分析计划 JSON 把方法、阈值、图表配置一次定死，可复现）、
**统计误用拦截**（样本量<30 做 t 检验、期望频数<5 做卡方，机器直接报警）、
**结论三段式**（数据+解读+局限，每条结论都有边界）。

## 3 个命令用法

| 命令 | 作用 | 示例 |
|---|---|---|
| `/lhg-survey:survey` | CSV→清洗→描述统计→交叉分析→图表→结论报告，一条龙 | `/lhg-survey:survey data/问卷.csv` |
| `/lhg-survey:survey-clean` | 只做数据清洗，输出清洗报告 | `/lhg-survey:survey-clean data/问卷.csv --plan plan.json` |
| `/lhg-survey:survey-audit` | 11 条规则审计 + 统计方法复核 | `/lhg-survey:survey-audit data/问卷.csv --plan plan.json` |

## 自查说明

自查 = 确定性脚本（机器）+ 方法复核（人）：

1. 先跑 `scripts/audit/survey_audit.py --target <CSV> --plan <分析计划.json>`，零成本；
2. 发现分两级：**blocker**（SV-CSV-001 无数据 / SV-COL-001 缺列，必须解决）、**warning**（缺失值/重复/逻辑矛盾/时长异常/非法值/统计误用/图表不一致/数字对不上，修或写豁免理由）；
3. 再按 `lhg-survey-stats` 选择树复核每个统计方法：t 检验要 2 组且每组 n≥30，卡方要期望频数≥5，相关要 n≥30 且都是数值变量。

blocker 清零才算"可发出"；为清零改脚本规则或阈值 → 作弊，不许。

## 分析计划 JSON（核心设计）

本插件的最大特点是"先定计划再动手"。分析计划长这样（见 `fixtures/bad_plan.json`）：

```json
{
  "expected_columns": ["age", "gender", "satisfaction"],
  "value_sets": {"gender": ["男", "女"]},
  "numeric_ranges": {"age": [0, 120], "satisfaction": [1, 5]},
  "logic_rules": [{"name": "未成年人已婚", "expr": "age < 18 and married == '是'"}],
  "duration_col": "duration_sec",
  "min_duration_sec": 30,
  "stats": [{"method": "t_test", "group_col": "gender", "value_col": "satisfaction"}],
  "charts": [{"title": "满意度分布", "type": "bar", "columns": ["satisfaction"]}],
  "summary_numbers": {"有效样本量": 120}
}
```

计划经用户确认后，清洗、统计、图表、审计全部按它执行——方法可复现，结论可追溯。

## 目录结构

```
lhg-survey/
├── .claude-plugin/          # plugin.json（插件清单）+ marketplace.json（本仓即市场）
├── commands/                # 3 个命令：survey / survey-clean / survey-audit
├── skills/                  # 4 个平台中立 skill（lhg-survey-clean/stats/charts/report）
├── agents/                  # 3 个专家 agent（data-cleaner / stats-analyst / report-writer）
├── hooks/                   # 2 个硬门（commit 前 CSV 审计拦截 / 写 CSV 提醒）+ 豁免说明
├── scripts/audit/           # 11 条确定性审计规则（零第三方依赖，纯标准库解析 CSV）
├── fixtures/                # 冒烟测试用例（bad/good CSV + 分析计划 + make_fixtures.py 生成器）
├── smoke_test.py            # 一键冒烟测试
├── ATTRIBUTION.md            # 灵感来源与许可声明
└── LICENSE                  # MIT
```

## 什么时候用 / 什么时候不用（FAQ）

**什么时候用：**

- 你刚收完一份问卷（几十到几百份），要出分析报告 → `/lhg-survey:survey`，CSV 丢进来就行
- 你只想先看看数据干不干净 → `/lhg-survey:survey-clean`，清洗报告告诉你删了多少、为什么
- 你不确定 t 检验/卡方用得对不对 → `/lhg-survey:survey-audit`，统计误用机器帮你拦
- 你的问卷是单选/量表为主的结构化问卷 → 本插件的主场

**什么时候不用：**

- 你的问卷全是开放题（访谈式）→ 本插件是结构化数据流水线，开放题只能做主题编码（见 lhg-survey-clean 第 7 节）
- 样本量 <30 → 描述统计可以，推断统计基本免谈，插件会如实告诉你"方法做不了"
- 你要的是 SPSS 级的复杂建模（回归/因子分析）→ 本插件覆盖 t 检验/卡方/相关/ANOVA，复杂建模不在范围内

**诚实声明：**

- 本插件的方法论为原创（2026-10-11 检索：组织内部百垂直调研 + 本地 skill 库均未找到问卷分析垂直 skill）。
- 插件保证的是流程标准化与误用拦截，不保证结论"显著"——数据不行，如实说不行。
- 统计结论的解读是推测不是事实，报告里的"局限"不是摆设。

## lhg-plugs 插件矩阵

| 插件 | 一句话 | 安装 |
|---|---|---|
| [lhg-survey](https://github.com/lhg-plugs/lhg-survey) | 问卷分析专家：CSV→清洗→统计→图表→报告一键生成 | `/plugin install lhg-survey@lhg-plugs` |
| *（后续插件在此追加，保持表格格式一致）* | | |

## 自检与反馈

本插件自带质检：每次使用后可跑 `python3 smoke_test.py` 一键验证（JSON 合法、skill/command/agent 完整性、11 条规则、fixtures 命中、hooks 行为）。

发现 bug 或有改进建议，以 `[QC] <一句话问题>` 为标题提交到 https://github.com/lhg-plugs/lhg-survey/issues，正文写清"复现步骤 → 实际表现 → 期望表现"。

## 出品：刘洪光

本插件由真人出镜 IP「刘洪光」（安徽合肥）出品，归属 [lhg-skills](https://github.com/lhg-skills)。

- GitHub 主页：https://github.com/lhg-skills —— 全部 skill 开源在此，欢迎 star
- 抖音：搜「刘老师讲AI实战」
- 微信：lhgsmsw
