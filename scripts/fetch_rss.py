#!/usr/bin/env python3
"""행정안전부 보도자료 RSS → 정적 사본(public/data/rss_snapshot.json) 저장

배포 빌드 때 실행되어, 브라우저에서 RSS를 직접 못 읽거나(CORS)
서버리스 프록시가 실패할 때 쓰는 '정적 사본'을 최신으로 갱신합니다.
네트워크 오류가 나면 기존 사본을 그대로 두고 0으로 종료합니다(빌드 중단 방지).

사용법:
    python scripts/fetch_rss.py
    python scripts/fetch_rss.py --url "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012" --limit 10
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
DEFAULT_URL = "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012"  # 보도자료
FEED_NAME = "행정안전부 보도자료"


def decode(raw: bytes) -> str:
    head = raw[:200].decode("ascii", "ignore")
    m = re.search(r'encoding=["\']([\w-]+)["\']', head, re.I)
    enc = (m.group(1) if m else "utf-8").lower()
    if enc in ("euc-kr", "ks_c_5601-1987"):
        enc = "cp949"
    return raw.decode(enc, "replace")


def norm_date(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        pass
    m = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", text)
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else text


def fetch(url: str, limit: int) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (integrity-portal build)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        xml_text = decode(r.read())
    xml_text = re.sub(r"<\?xml[^>]*\?>", "", xml_text, count=1)  # 인코딩 선언 제거 후 파싱
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if title and link:
            items.append({"title": title, "link": link, "date": norm_date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "")})
        if len(items) >= limit:
            break
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default="public/data/rss_snapshot.json")
    a = ap.parse_args()
    out = Path(a.out)
    try:
        items = fetch(a.url, a.limit)
        if len(items) < 5:
            raise RuntimeError(f"항목이 {len(items)}건뿐입니다")
    except Exception as e:  # noqa: BLE001 - 빌드를 멈추지 않기 위해 모든 오류 처리
        print(f"[warn] RSS 수집 실패, 기존 사본 유지: {e}", file=sys.stderr)
        return 0
    payload = {"feed": FEED_NAME, "source": a.url,
               "collectedAt": datetime.now(KST).isoformat(timespec="seconds"), "items": items}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[ok] {out} ({len(items)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
