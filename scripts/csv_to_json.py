#!/usr/bin/env python3
"""청렴 신고·교육 CSV → 웹 페이지용 JSON 변환기 (표준 라이브러리만 사용)

사용법:
    python scripts/csv_to_json.py            # data/*.csv → public/data/*.json
    python scripts/csv_to_json.py --src data --out public/data

- UTF-8 BOM 자동 제거, 빈 값은 null 로 저장
- 숫자 열은 int/float 로 변환
- 사건은 신고일자 최신순으로 정렬
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))

CASE_FILE = "청렴신고_사건데이터.csv"
EDU_FILE = "청렴교육_현황.csv"

CASE_INT = {"처리기간_일", "위반금액_만원"}
EDU_INT = {"연간교육시간", "교육참여자수"}
EDU_FLOAT = {"교육이수율"}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [{k.strip(): (v.strip() if v is not None else "") for k, v in row.items()}
                for row in csv.DictReader(f)]


def to_num(value: str, kind):
    if value == "":
        return None
    try:
        return kind(float(value)) if kind is int else kind(value)
    except ValueError:
        return None


def convert_cases(rows):
    out = []
    for r in rows:
        out.append({
            "id": r["사건ID"],
            "date": r["신고일자"],
            "type": r["신고유형"],
            "region": r["지역"],
            "reporter": r["신고자유형"],
            "status": r["처리상태"],
            "days": to_num(r["처리기간_일"], int),
            "amount": to_num(r["위반금액_만원"], int),
            "result": r["조치결과"],
        })
    out.sort(key=lambda c: (c["date"], c["id"]), reverse=True)
    return out


def convert_edu(rows):
    return [{
        "code": r["기관코드"],
        "name": r["기관명"],
        "orgType": r["기관유형"],
        "completion": to_num(r["교육이수율"], float),
        "hours": to_num(r["연간교육시간"], int),
        "participants": to_num(r["교육참여자수"], int),
        "excellent": r["청렴우수기관"].upper() == "Y",
    } for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="data")
    ap.add_argument("--out", default="public/data")
    a = ap.parse_args()

    src, out = Path(a.src), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(KST).isoformat(timespec="seconds")

    cases = convert_cases(read_csv(src / CASE_FILE))
    edu = convert_edu(read_csv(src / EDU_FILE))

    for name, items in (("cases.json", cases), ("education.json", edu)):
        payload = {"generatedAt": generated, "count": len(items), "items": items}
        (out / name).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[ok] {out / name}  ({len(items)}건)")


if __name__ == "__main__":
    main()
