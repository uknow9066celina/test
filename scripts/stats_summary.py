#!/usr/bin/env python3
"""CSV 자동 통계 요약 도구 (표준 라이브러리만 사용, Python 3.9+)

어떤 CSV든 열 유형을 자동 판별해 요약하고, 청렴 신고·교육 데이터면
업무용 지표(유형별·상태별 건수, 처리기간, 이수율 등)를 추가로 계산합니다.

사용법:
    python scripts/stats_summary.py data/청렴신고_사건데이터.csv data/청렴교육_현황.csv
    python scripts/stats_summary.py data/*.csv --out reports
    python scripts/stats_summary.py 아무파일.csv --top 5 --quiet

출력:
    reports/<파일명>_요약.md    사람이 읽는 보고서
    reports/<파일명>_요약.json  다른 시스템에서 쓰는 기계용 결과
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ───────────────────────── 공통 유틸 ─────────────────────────
def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    for enc in ("utf-8-sig", "cp949"):
        try:
            with path.open(encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]
                return [c.strip() for c in reader.fieldnames or []], rows
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 읽을 수 없습니다: {path}")


def num(v: str):
    if v == "":
        return None
    try:
        f = float(v.replace(",", ""))
        return f if math.isfinite(f) else None
    except ValueError:
        return None


def infer_type(values: list[str]) -> str:
    filled = [v for v in values if v != ""]
    if not filled:
        return "empty"
    if all(DATE_RE.match(v) for v in filled):
        return "date"
    if all(num(v) is not None for v in filled):
        return "numeric"
    return "categorical"


def quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    pos = (len(sorted_vals) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def numeric_stats(vals: list[float]) -> dict:
    s = sorted(vals)
    q1, q3 = quantile(s, .25), quantile(s, .75)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {
        "count": len(s), "mean": round(st.fmean(s), 2), "median": round(st.median(s), 2),
        "std": round(st.pstdev(s), 2) if len(s) > 1 else 0.0,
        "min": s[0], "q1": round(q1, 2), "q3": round(q3, 2), "p90": round(quantile(s, .9), 2), "max": s[-1],
        "sum": round(sum(s), 2),
        "outlier_rule": f"IQR 1.5배 (<{round(lo, 2)} 또는 >{round(hi, 2)})",
        "outliers": [v for v in s if v < lo or v > hi],
    }


def fmt(n, digits=1):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "-"
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.{digits}f}"
    return f"{int(n):,}"


def pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "-"


def counter_table(c: Counter, total: int, label: str, top: int | None = None) -> list[str]:
    lines = [f"| {label} | 건수 | 비율 |", "|---|---:|---:|"]
    for k, v in c.most_common(top):
        lines.append(f"| {k or '(빈 값)'} | {v:,} | {pct(v, total)} |")
    return lines


# ───────────────────────── 범용 프로파일 ─────────────────────────
def profile(cols: list[str], rows: list[dict], top: int) -> dict:
    n = len(rows)
    out = {"rows": n, "columns": {}}
    for c in cols:
        vals = [r.get(c, "") for r in rows]
        t = infer_type(vals)
        missing = sum(1 for v in vals if v == "")
        info = {"type": t, "missing": missing, "missing_rate": round(missing / n * 100, 1) if n else 0}
        filled = [v for v in vals if v != ""]
        if t == "numeric":
            info["stats"] = numeric_stats([num(v) for v in filled])
        elif t == "date":
            info["min"], info["max"] = min(filled), max(filled)
            info["by_year"] = dict(sorted(Counter(v[:4] for v in filled).items()))
        elif t == "categorical":
            cnt = Counter(filled)
            info["unique"] = len(cnt)
            info["top"] = cnt.most_common(top)
            if len(cnt) == n:
                info["note"] = "모든 값이 고유 (식별자 열로 추정)"
        out["columns"][c] = info
    return out


def profile_md(p: dict) -> list[str]:
    L = ["## 1. 열 구성과 결측치", "", "| 열 | 유형 | 결측 | 요약 |", "|---|---|---:|---|"]
    tname = {"numeric": "숫자", "date": "날짜", "categorical": "범주", "empty": "빈 열"}
    for c, i in p["columns"].items():
        if i["type"] == "numeric":
            s = i["stats"]
            summ = f"평균 {fmt(s['mean'])} · 중앙값 {fmt(s['median'])} · 범위 {fmt(s['min'])}~{fmt(s['max'])}"
        elif i["type"] == "date":
            summ = f"{i['min']} ~ {i['max']}"
        elif i["type"] == "categorical":
            summ = i.get("note") or f"{i['unique']}종 · 최다 '{i['top'][0][0]}'({i['top'][0][1]}건)"
        else:
            summ = "-"
        L.append(f"| {c} | {tname[i['type']]} | {i['missing']} ({i['missing_rate']}%) | {summ} |")
    L.append("")
    nums = {c: i for c, i in p["columns"].items() if i["type"] == "numeric"}
    if nums:
        L += ["## 2. 숫자 열 상세", "", "| 열 | 평균 | 중앙값 | 표준편차 | Q1 | Q3 | 상위10% | 최대 | 이상치 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for c, i in nums.items():
            s = i["stats"]
            L.append(f"| {c} | {fmt(s['mean'])} | {fmt(s['median'])} | {fmt(s['std'])} | {fmt(s['q1'])} | {fmt(s['q3'])} | "
                     f"{fmt(s['p90'])} | {fmt(s['max'])} | {len(s['outliers'])}건 |")
        L += ["", "> 이상치 기준: 사분위범위(IQR)의 1.5배를 벗어난 값", ""]
    return L


# ───────────────────────── 청렴 신고 사건 ─────────────────────────
def is_cases(cols):
    return {"사건ID", "신고유형", "처리상태"}.issubset(cols)


def analyze_cases(rows: list[dict], top: int) -> tuple[dict, list[str]]:
    n = len(rows)
    by_type = Counter(r["신고유형"] for r in rows)
    by_status = Counter(r["처리상태"] for r in rows)
    by_region = Counter(r["지역"] for r in rows)
    by_reporter = Counter(r["신고자유형"] for r in rows)
    by_year = Counter(r["신고일자"][:4] for r in rows if r["신고일자"])
    by_month = Counter(r["신고일자"][:7] for r in rows if r["신고일자"])

    closed = {"처리완료", "기각", "이첩"}
    done = sum(v for k, v in by_status.items() if k in closed)

    days_by_type = defaultdict(list)
    for r in rows:
        d = num(r.get("처리기간_일", ""))
        if d is not None:
            days_by_type[r["신고유형"]].append(d)
    all_days = [d for v in days_by_type.values() for d in v]
    days_stats = numeric_stats(all_days)
    long_cases = sorted(((r["사건ID"], r["신고유형"], r["지역"], int(num(r["처리기간_일"]))) for r in rows
                         if num(r.get("처리기간_일", "")) is not None and num(r["처리기간_일"]) > days_stats["p90"] * 2),
                        key=lambda x: -x[3])

    amts = [num(r["위반금액_만원"]) for r in rows if num(r.get("위반금액_만원", "")) is not None]
    amt_stats = numeric_stats(amts)
    big = sorted(((r["사건ID"], r["신고유형"], r["지역"], r["처리상태"], int(num(r["위반금액_만원"]))) for r in rows
                  if num(r.get("위반금액_만원", "")) is not None and num(r["위반금액_만원"]) >= 10000),
                 key=lambda x: -x[4])

    # 처리상태 ↔ 조치결과 일관성 점검
    expected = {"처리완료": "징계·경고", "이첩": "검찰이첩", "기각": "불문", "조사중": "해당없음", "접수완료": "해당없음"}
    mismatch = [r["사건ID"] for r in rows if r["처리상태"] in expected and r["조치결과"] != expected[r["처리상태"]]]

    cross = defaultdict(Counter)
    for r in rows:
        cross[r["신고유형"]][r["처리상태"]] += 1
    statuses = [s for s, _ in by_status.most_common()]

    res = {
        "total": n, "closed": done, "closed_rate": round(done / n * 100, 1) if n else 0,
        "by_type": dict(by_type.most_common()), "by_status": dict(by_status.most_common()),
        "by_region": dict(by_region.most_common()), "by_reporter": dict(by_reporter.most_common()),
        "by_year": dict(sorted(by_year.items())), "by_month": dict(sorted(by_month.items())),
        "days": days_stats, "days_median_by_type": {k: st.median(v) for k, v in sorted(days_by_type.items())},
        "long_cases": long_cases, "amount_10k_won": amt_stats, "big_amount_cases": big,
        "status_result_mismatch": mismatch, "type_x_status": {k: dict(v) for k, v in cross.items()},
    }

    L = ["## 3. 청렴 신고 사건 핵심 지표", "",
         f"- 전체 신고 **{n:,}건**, 종결(처리완료·이첩·기각) **{done:,}건 ({res['closed_rate']}%)**, "
         f"진행 중(접수완료·조사중) **{n - done:,}건**",
         f"- 신고 기간: {min(r['신고일자'] for r in rows)} ~ {max(r['신고일자'] for r in rows)}",
         f"- 처리기간 중앙값 **{fmt(days_stats['median'])}일**, 평균 {fmt(days_stats['mean'])}일, 상위 10% {fmt(days_stats['p90'])}일 이상",
         f"- 위반금액 중앙값 **{fmt(amt_stats['median'])}만원**, 합계 {fmt(amt_stats['sum'])}만원 (결측 {n - len(amts)}건 제외)",
         ""]
    L += ["### 신고유형별", ""] + counter_table(by_type, n, "신고유형") + [""]
    L += ["### 처리상태별", ""] + counter_table(by_status, n, "처리상태") + [""]
    L += ["### 신고유형 × 처리상태", "", "| 신고유형 | " + " | ".join(statuses) + " | 합계 |",
          "|---|" + "---:|" * (len(statuses) + 1)]
    for t, _ in by_type.most_common():
        L.append(f"| {t} | " + " | ".join(str(cross[t].get(s, 0)) for s in statuses) + f" | {by_type[t]} |")
    L += ["", f"### 지역별 (상위 {top})", ""] + counter_table(by_region, n, "지역", top) + [""]
    L += ["### 신고자유형별", ""] + counter_table(by_reporter, n, "신고자유형") + [""]
    L += ["### 연도별 신고 건수", "", "| 연도 | 건수 |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in sorted(by_year.items())]
    L += ["", "### 신고유형별 처리기간 중앙값", "", "| 신고유형 | 중앙값(일) |", "|---|---:|"]
    L += [f"| {k} | {fmt(v)} |" for k, v in sorted(res["days_median_by_type"].items(), key=lambda x: -x[1])]
    L += ["", "## 4. 확인이 필요한 항목", ""]
    L.append(f"- **장기 처리 사건** (상위 10% 기준의 2배인 {fmt(days_stats['p90'] * 2)}일 초과): {len(long_cases)}건")
    L += [f"  - {i} · {t} · {r} · {d}일" for i, t, r, d in long_cases]
    L.append(f"- **고액 위반 사건** (1억원 = 10,000만원 이상): {len(big)}건")
    L += [f"  - {i} · {t} · {r} · {s} · {a:,}만원" for i, t, r, s, a in big]
    L.append(f"- **처리상태와 조치결과 불일치**: {len(mismatch)}건" + (f" ({', '.join(mismatch[:10])})" if mismatch else ""))
    L.append("")
    return res, L


# ───────────────────────── 청렴 교육 현황 ─────────────────────────
def is_edu(cols):
    return {"기관코드", "교육이수율"}.issubset(cols)


def pearson(xs, ys):
    if len(xs) < 3:
        return float("nan")
    try:
        return st.correlation(xs, ys)
    except (st.StatisticsError, AttributeError):
        return float("nan")


def analyze_edu(rows: list[dict], top: int) -> tuple[dict, list[str]]:
    n = len(rows)
    rates = [(r, num(r["교육이수율"])) for r in rows]
    valid = [(r, v) for r, v in rates if v is not None]
    missing = [r["기관코드"] for r, v in rates if v is None]
    rs = numeric_stats([v for _, v in valid])

    by_type = defaultdict(list)
    for r, v in valid:
        by_type[r["기관유형"]].append(v)
    exc = [r for r in rows if r["청렴우수기관"].upper() == "Y"]
    exc_rates = [num(r["교육이수율"]) for r in exc if num(r["교육이수율"]) is not None]
    non_rates = [v for r, v in valid if r["청렴우수기관"].upper() != "Y"]
    min_exc = min(exc_rates) if exc_rates else None

    bands = Counter()
    for _, v in valid:
        bands["90% 이상" if v >= 90 else "80~90%" if v >= 80 else "70~80%" if v >= 70 else "60~70%" if v >= 60 else "60% 미만"] += 1

    hrs = [(num(r["연간교육시간"]), v) for r, v in valid if num(r["연간교육시간"]) is not None]
    corr = pearson([h for h, _ in hrs], [v for _, v in hrs])

    prefix_map = {"중앙기관": "중앙행정기관", "지방기관": "지방자치단체", "공공기관": "공공기관", "교육기관": "교육기관"}
    name_mismatch = [r["기관코드"] for r in rows
                     for p, t in prefix_map.items() if r["기관명"].startswith(p) and r["기관유형"] != t]
    low = sorted(((r["기관코드"], r["기관명"], r["기관유형"], v) for r, v in valid if v < 60), key=lambda x: x[3])
    participants = sum(int(num(r["교육참여자수"]) or 0) for r in rows)

    res = {
        "total": n, "rate": rs, "missing_rate_codes": missing,
        "by_org_type": {k: {"count": len(v), "mean": round(st.fmean(v), 1)} for k, v in sorted(by_type.items())},
        "excellent": {"count": len(exc), "mean_rate": round(st.fmean(exc_rates), 1) if exc_rates else None,
                      "min_rate": min_exc},
        "non_excellent_mean_rate": round(st.fmean(non_rates), 1) if non_rates else None,
        "bands": dict(bands), "hours_rate_corr": None if math.isnan(corr) else round(corr, 3),
        "participants_total": participants, "low_rate_orgs": low, "name_type_mismatch": name_mismatch,
    }

    L = ["## 3. 청렴 교육 핵심 지표", "",
         f"- 대상 기관 **{n}곳**, 교육 참여자 합계 **{participants:,}명**",
         f"- 교육이수율 평균 **{fmt(rs['mean'])}%**, 중앙값 {fmt(rs['median'])}% (이수율 미기재 {len(missing)}곳 제외)",
         f"- 청렴우수기관 **{len(exc)}곳** ({pct(len(exc), n)}), 우수기관 평균 이수율 {res['excellent']['mean_rate']}% "
         f"vs 일반기관 {res['non_excellent_mean_rate']}%",
         f"- 연간교육시간과 이수율의 상관계수 r = {fmt(corr, 3)}"
         + (" (사실상 상관 없음)" if not math.isnan(corr) and abs(corr) < 0.2 else ""),
         ""]
    if min_exc is not None:
        L.insert(-1, f"- 우수기관은 모두 이수율 {fmt(min_exc)}% 이상 (선정 기준이 이수율 90% 내외로 보임)")
    L += ["### 기관유형별 평균 이수율", "", "| 기관유형 | 기관 수 | 평균 이수율 |", "|---|---:|---:|"]
    L += [f"| {k} | {v['count']} | {v['mean']}% |" for k, v in sorted(res["by_org_type"].items(), key=lambda x: -x[1]["mean"])]
    order = ["90% 이상", "80~90%", "70~80%", "60~70%", "60% 미만"]
    L += ["", "### 이수율 구간 분포", "", "| 구간 | 기관 수 |", "|---|---:|"] + [f"| {b} | {bands.get(b, 0)} |" for b in order]
    L += ["", "## 4. 확인이 필요한 항목", "",
          f"- **이수율 60% 미만 기관**: {len(low)}곳"]
    L += [f"  - {c} {nm} ({t}) {v}%" for c, nm, t, v in low[:top * 2]]
    if len(low) > top * 2:
        L.append(f"  - … 외 {len(low) - top * 2}곳 (JSON 참고)")
    L.append(f"- **교육이수율 미기재**: {len(missing)}곳 ({', '.join(missing)})")
    L.append(f"- **기관명과 기관유형 불일치** (예: '중앙기관'인데 유형이 '지방자치단체'): {len(name_mismatch)}곳 "
             "— 기관명이 가명 처리된 데이터일 수 있으니 원본 확인 필요")
    L.append("")
    return res, L


# ───────────────────────── 실행 ─────────────────────────
def summarize(path: Path, out_dir: Path, top: int, quiet: bool) -> Path:
    cols, rows = read_csv(path)
    if not rows:
        raise ValueError("데이터 행이 없습니다")
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    p = profile(cols, rows, top)
    result = {"file": path.name, "generatedAt": now, "profile": p}
    md = [f"# {path.stem} 통계 요약", "", f"- 원본: `{path.name}` · {len(rows):,}행 × {len(cols)}열",
          f"- 생성: {now} (KST) · 생성 도구: stats_summary.py", ""]
    md += profile_md(p)

    if is_cases(cols):
        res, lines = analyze_cases(rows, top)
        result["domain"] = {"kind": "청렴신고", **res}
        md += lines
    elif is_edu(cols):
        res, lines = analyze_edu(rows, top)
        result["domain"] = {"kind": "청렴교육", **res}
        md += lines

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{path.stem}_요약.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    (out_dir / f"{path.stem}_요약.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if not quiet:
        print("\n".join(md))
    print(f"[ok] {md_path}", file=sys.stderr)
    return md_path


def main():
    ap = argparse.ArgumentParser(description="CSV 자동 통계 요약", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("files", nargs="+", type=Path, help="요약할 CSV 파일")
    ap.add_argument("--out", type=Path, default=Path("reports"), help="보고서 저장 폴더 (기본: reports)")
    ap.add_argument("--top", type=int, default=10, help="상위 항목 표시 개수 (기본: 10)")
    ap.add_argument("--quiet", action="store_true", help="화면 출력 없이 파일만 저장")
    a = ap.parse_args()
    failed = 0
    for f in a.files:
        try:
            summarize(f, a.out, a.top, a.quiet)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[error] {f}: {e}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
