#!/usr/bin/env python3
"""生成 lhg-survey 冒烟测试 fixtures：
bad.csv + bad_plan.json（埋 11 类问题）、good.csv + good_plan.json（干净）。"""
import csv
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
HEADER = ["id", "age", "gender", "married", "satisfaction", "duration_sec"]


def write_csv(name, rows):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)


def write_plan(name, plan):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def base_plan():
    return {
        "expected_columns": ["id", "age", "gender", "married", "satisfaction", "duration_sec"],
        "value_sets": {"gender": ["男", "女"], "married": ["是", "否"]},
        "numeric_ranges": {"age": [0, 120], "satisfaction": [1, 5], "duration_sec": [0, 3600]},
        "logic_rules": [{"name": "未成年人已婚", "expr": "age < 18 and married == '是'"}],
        "missing_threshold": 0.2,
        "duplicate_threshold": 0.05,
        "duration_col": "duration_sec",
        "min_duration_sec": 30,
        "stats": [],
        "charts": [],
        "summary_numbers": {},
    }


def make_bad():
    rnd = random.Random(20261011)
    rows = []
    # 56 个基础行：0-19 男，20-55 女
    for i in range(56):
        gender = "男" if i < 20 else "女"
        age = rnd.randint(20, 65)
        married = "否"
        satisfaction = rnd.randint(1, 5)
        duration = rnd.randint(60, 600)
        rows.append([i + 1, age, gender, married, satisfaction, duration])

    # 埋点 1：逻辑矛盾（未成年人已婚）——行 2、3（0-based）
    for i in (2, 3):
        rows[i][1] = 16
        rows[i][3] = "是"
    # 埋点 2：已婚（卡方稀疏格用）——行 22、23、24
    for i in (22, 23, 24):
        rows[i][3] = "是"
    # 埋点 3：年龄越界 ——行 5
    rows[5][1] = 200
    # 埋点 4：性别非法值 ——行 6、7、8
    for i in (6, 7, 8):
        rows[i][2] = "未知"
    # 埋点 5：填答时长异常 ——行 11、12、13
    for i in (11, 12, 13):
        rows[i][5] = 5
    # 埋点 6：满意度缺失 25% ——5 个男行 + 10 个女行
    for i in (0, 4, 9, 14, 18, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34):
        rows[i][4] = ""
    # 埋点 7：列数不一致 ——行 30（0-based）砍掉 2 列
    rows[30] = rows[30][:4]
    # 埋点 8：完全重复行 ——复制行 0、1、20、21
    for i in (0, 1, 20, 21):
        rows.append(list(rows[i]))

    write_csv("bad.csv", rows)

    plan = base_plan()
    plan["expected_columns"] = HEADER + ["occupation"]  # 埋点：缺列
    plan["stats"] = [
        {"method": "t_test", "group_col": "gender", "value_col": "satisfaction"},
        {"method": "chi_square", "col_a": "gender", "col_b": "married"},
        {"method": "correlation", "col_x": "gender", "col_y": "satisfaction"},
    ]
    plan["charts"] = [
        {"title": "满意度分布", "type": "bar", "columns": ["satisfaction"]},
        {"title": "NPS 趋势", "type": "line", "columns": ["NPS"]},  # 埋点：列不存在
    ]
    plan["summary_numbers"] = {"有效样本量": 60}  # 埋点：实际 59（1 行列数异常被剔除）
    write_plan("bad_plan.json", plan)
    print("bad.csv: %d 行(含1行列数异常), bad_plan.json 已生成" % len(rows))


def make_good():
    rnd = random.Random(20261012)
    rows = []
    for i in range(120):
        gender = "男" if i < 60 else "女"
        age = rnd.randint(20, 65)
        married = "是" if (i % 3 == 0) else "否"  # 是 40 / 否 80，均匀分布
        satisfaction = rnd.randint(1, 5)
        duration = rnd.randint(60, 600)
        rows.append([i + 1, age, gender, married, satisfaction, duration])
    # 少量缺失（2.5%，低于阈值）
    for i in (10, 50, 90):
        rows[i][4] = ""
    write_csv("good.csv", rows)

    plan = base_plan()
    plan["stats"] = [
        {"method": "t_test", "group_col": "gender", "value_col": "satisfaction"},
        {"method": "chi_square", "col_a": "gender", "col_b": "married"},
        {"method": "correlation", "col_x": "age", "col_y": "satisfaction"},
    ]
    plan["charts"] = [
        {"title": "满意度分布", "type": "bar", "columns": ["satisfaction"]},
        {"title": "年龄-满意度散点", "type": "scatter", "columns": ["age", "satisfaction"]},
    ]
    plan["summary_numbers"] = {"有效样本量": 120}
    write_plan("good_plan.json", plan)
    print("good.csv: %d 行, good_plan.json 已生成" % len(rows))


if __name__ == "__main__":
    make_bad()
    make_good()
