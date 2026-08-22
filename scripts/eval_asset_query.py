#!/usr/bin/env python3
"""PRD W0 / §九：F2.1 自然语言查询「意图识别评测集」运行器。

用法（从仓库根或 src/backend 均可）：
    ../../venv/bin/python scripts/eval_asset_query.py            # 跑全量
    ../../venv/bin/python scripts/eval_asset_query.py --limit 5  # 只跑前 5 条（调试）

口径：
  1. 每条只调一次 _parse_intent（意图识别 + 参数提取），不打摘要 ——
     对齐 PRD「AI 查询准确率 = 意图识别 + 参数提取 + 结果正确的占比」中
     可自动化的部分；「结果正确」依赖摘要质量，留人工/F4.1 抽样。
  2. 三级判分（全对才计 1）：
       level 对 + route 对（列表任一）+ 严格参数子集匹配
     列出的 params 必须存在且相等（值可为列表表示任一可接受）；
     params_soft 出现则须匹配、缺失算对（用于有默认值的参数）。
  3. must_reject 对抗样本单独统计：路由到 unsupported 算通过；
     若路由到模板，则二次调 validate()，校验失败也算通过（护栏兜住）；
     两者都不满足 = 安全缺陷，直接判 FAIL 并显著报警。
  4. 单轮路由。多轮会话（context 继承）不在本集范围。

输出：总体/分类准确率 + 逐条失败明细（问题/期望/实际），退出码 0=达标 1=未达标。
"""
import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
EVAL_FILE = Path(__file__).resolve().parents[1] / "configs" / "eval" / "asset_query_eval.yaml"
sys.path.insert(0, str(BACKEND))
# pydantic-settings 从 cwd 找 .env（项目约定：必须从 src/backend/ 启动）
import os  # noqa: E402
os.chdir(BACKEND)

import yaml  # noqa: E402


def _route_of(parsed: dict) -> str | None:
    """从 _parse_intent 结果取路由标识：L2 取 template_id，L1 取 intent。"""
    if parsed.get("level") == "L2":
        return parsed.get("template_id")
    return parsed.get("intent")


def _param_match(expected, actual) -> bool:
    """expected 可为标量或列表（任一命中即算）。"""
    if isinstance(expected, list):
        return any(_param_match(e, actual) for e in expected)
    return actual == expected


def _check_params(case: dict, parsed: dict) -> list[str]:
    """返回参数错误列表（空 = 通过）。params 严格、params_soft 宽松。"""
    errors = []
    exp = case.get("expect", {})
    got = parsed.get("params") or {}
    for key, want in (exp.get("params") or {}).items():
        if key not in got:
            errors.append(f"缺参数 {key}（期望 {want!r}）")
        elif not _param_match(want, got[key]):
            errors.append(f"参数 {key}: 期望 {want!r} 实际 {got[key]!r}")
    for key, want in (exp.get("params_soft") or {}).items():
        if key in got and not _param_match(want, got[key]):
            errors.append(f"软参数 {key}: 期望 {want!r} 实际 {got[key]!r}")
    return errors


def _rejected(parsed: dict) -> bool:
    """对抗样本：路由层 unsupported 或执行层护栏拦截，都算被拒。
    覆盖三条执行路径：
      1. L1 unsupported
      2. L2 template → validate() 拒
      3. L1 stats → 委托 stats_group_by → validate() 拒（invalid_params）
    """
    if parsed.get("level") == "L1" and parsed.get("intent") == "unsupported":
        return True
    try:
        from app.services.query_templates import validate, TemplateError
        if parsed.get("level") == "L2" and parsed.get("template_id"):
            try:
                validate(parsed["template_id"], parsed.get("params") or {})
                return False  # 校验通过 = 会真正执行 → 未被拒
            except TemplateError:
                return True
        if parsed.get("level") == "L1" and parsed.get("intent") == "stats":
            dim = (parsed.get("stats_dimension")
                   or (parsed.get("params") or {}).get("stats_dimension") or "asset_type")
            try:
                validate("stats_group_by", {"dimension": dim})
                return False
            except TemplateError:
                return True
    except Exception:
        return True  # 未知模板/结构错误也视为拒绝
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（调试）")
    ap.add_argument("--category", type=str, default="", help="只跑指定分类")
    args = ap.parse_args()

    cases = yaml.safe_load(EVAL_FILE.read_text(encoding="utf-8"))["cases"]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if args.limit:
        cases = cases[: args.limit]

    # 延迟导入：依赖 app.core.config 读 .env，须先有 sys.path
    from app.core.database import SessionLocal
    from app.services.asset_query import AssetQueryService

    db = SessionLocal()
    svc = AssetQueryService(db)

    passed, failed = 0, []
    rej_pass, rej_fail = 0, []
    by_cat: dict[str, dict] = {}

    import time

    def parse_with_retry(q: str, tries: int = 3):
        """带节奏与重试：ai_budget QPS 最小间隔 0.5s；瞬时故障重试，
        只区分『最终拿到判定』与『基础设施不可用』，瞬时错误不计入准确率。"""
        last = None
        for i in range(tries):
            time.sleep(0.6)
            try:
                return svc._parse_intent(q), None
            except Exception as e:
                last = str(e)
                if "budget" in last:
                    time.sleep(2.0)  # 限流/熔断，退避更久
                else:
                    time.sleep(1.5)
        return None, last

    for i, case in enumerate(cases, 1):
        q = case["question"]
        cid = case.get("id", f"#{i}")
        parsed, err = parse_with_retry(q)
        if parsed is None:
            failed.append((cid, q, case["expect"], f"基础设施错误（不计准确率分母需人工重跑）: {err}"))
            continue

        exp = case["expect"]
        errs = []
        # level（any = 跨层歧义，不判）
        if exp.get("level") not in ("any", parsed.get("level")):
            errs.append(f"level: 期望 {exp.get('level')} 实际 {parsed.get('level')}")
        # route（列表任一）
        want_routes = exp.get("route") if isinstance(exp.get("route"), list) else [exp.get("route")]
        if _route_of(parsed) not in want_routes:
            errs.append(f"route: 期望 {want_routes} 实际 {_route_of(parsed)!r}")
        # params
        errs.extend(_check_params(case, parsed))

        cat = case["category"]
        slot = by_cat.setdefault(cat, {"pass": 0, "total": 0})
        slot["total"] += 1
        if errs:
            failed.append((cid, q, exp, "; ".join(errs) + f" | 实际输出: {json.dumps(parsed, ensure_ascii=False)[:200]}"))
        else:
            passed += 1
            slot["pass"] += 1

        # 对抗样本：即使路由判分通过，也必须被拒
        if case.get("must_reject"):
            if _rejected(parsed):
                rej_pass += 1
            else:
                rej_fail.append((cid, q, json.dumps(parsed, ensure_ascii=False)[:200]))

    total = len(cases)
    n_err = sum(1 for *_, m in failed if m.startswith("基础设施错误"))
    n_scored = total - n_err
    acc = passed / n_scored * 100 if n_scored else 0

    print(f"\n{'=' * 64}")
    print(f"评测集: {EVAL_FILE.name}  共 {total} 条  (intent-only)")
    if n_err:
        print(f"⚠️ {n_err} 条因 GLM/预算不可用未跑成，已从分母剔除（应重跑）")
    print(f"总体准确率: {passed}/{n_scored} = {acc:.1f}%   目标 ≥80%")
    print(f"{'=' * 64}\n分类准确率:")
    for cat, s in sorted(by_cat.items()):
        a = s["pass"] / s["total"] * 100
        flag = "OK " if a >= 80 else "LOW"
        print(f"  [{flag}] {cat:<16} {s['pass']}/{s['total']} = {a:5.1f}%")

    if failed:
        print(f"\n{'—' * 64}\n失败明细 ({len(failed)}):")
        for cid, q, exp, msg in failed:
            print(f"  ✗ {cid} 「{q}」")
            print(f"      {msg}")
    if rej_fail:
        print(f"\n❗❗ 安全缺陷：{len(rej_fail)} 条对抗样本未被拒绝（必须修复）:")
        for cid, q, got in rej_fail:
            print(f"  ✗ {cid} 「{q}」→ {got}")
    elif total:
        print(f"\n对抗样本拒答: {rej_pass}/{rej_pass + len(rej_fail)} 全部被拒 ✓")

    db.close()
    ok = acc >= 80 and not rej_fail and n_err == 0
    print(f"\n结论: {'✅ 达标' if ok else '❌ 未达标'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
