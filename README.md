# 청렴 신고 사건 조회 — 시민 공개 페이지 + 통계 자동화 도구

행정안전부 청렴감사관실 공개용 정적 웹 페이지와 CSV 통계 요약 스크립트입니다.

```
integrity-portal/
├─ data/                      원본 CSV (청렴신고_사건데이터.csv, 청렴교육_현황.csv)
├─ public/                    배포되는 정적 사이트
│  ├─ index.html              조회 페이지 (<title>청렴 신고 사건 조회</title>)
│  └─ data/                   cases.json · education.json · rss_snapshot.json
├─ scripts/
│  ├─ csv_to_json.py          CSV → JSON 변환 (빌드 시 자동 실행)
│  ├─ fetch_rss.py            행안부 RSS → 정적 사본 저장 (빌드 시 자동 실행)
│  └─ stats_summary.py        CSV 자동 통계 요약 (Markdown + JSON 보고서)
├─ netlify/functions/rss.mjs  Netlify 서버리스 RSS 프록시 (/api/rss)
├─ api/rss.mjs                Vercel 서버리스 RSS 프록시 (/api/rss)
├─ api/_rss-parse.mjs         두 프록시가 함께 쓰는 RSS 파서
├─ netlify.toml · vercel.json 배포 설정
└─ reports/                   stats_summary.py 결과물
```

## 1. 페이지 기능

| 요구사항 | 구현 |
|---|---|
| 제목에 "청렴"·"신고" | `<title>청렴 신고 사건 조회</title>` |
| 사건 카드 | 신고일자·신고유형·지역·처리상태(색 구분 배지) + 처리기간 |
| 검색·필터 | 신고유형 칩, 처리상태 칩(상단 현황 막대 범례로도 선택), 지역, 사건번호·지역 검색, 정렬 |
| 결과 건수 | `결과 N건` 실시간 표시 |
| RSS 임베드 | 행정안전부 보도자료 RSS 최신 8건(제목·날짜·링크) |

### RSS를 불러오는 순서 (CORS 대응)

1. **서버리스 프록시** `/api/rss` — 서버에서 `https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012`를 받아 JSON으로 전달 (EUC-KR/UTF-8 자동 판별, 30분 캐시)
2. 실패하면 **정적 사본** `data/rss_snapshot.json` — 배포 빌드 때 `fetch_rss.py`가 갱신

배지에 "실시간" 또는 "정적 사본 · 수집일"이 표시되어 어느 쪽인지 알 수 있습니다.
다른 피드(예: 설명자료)로 바꾸려면 두 프록시 파일과 `fetch_rss.py`의 `FEED_URL`/`DEFAULT_URL`만 수정하세요.

## 2. 배포

### Netlify (가장 쉬운 방법: Git 연결)
1. 이 폴더를 GitHub 저장소에 올립니다.
2. app.netlify.com → **Add new site → Import an existing project** → 저장소 선택
3. 설정은 `netlify.toml`이 자동 적용(빌드 명령·publish 폴더·functions) → **Deploy**

CLI로 할 경우:
```bash
npm i -g netlify-cli
netlify login
netlify deploy --prod      # 저장소 루트에서 실행
```

> Netlify Drop(폴더 끌어놓기)은 서버리스 함수를 올리지 않으므로, 그 경우 RSS는 정적 사본으로 표시됩니다.

### Vercel
```bash
npm i -g vercel
vercel --prod              # 저장소 루트에서 실행, vercel.json 자동 적용
```
또는 vercel.com → **Add New → Project** → 저장소 가져오기 (Framework Preset: Other).

## 3. 통계 요약 도구

```bash
python scripts/stats_summary.py data/*.csv               # 화면 출력 + reports/ 저장
python scripts/stats_summary.py data/*.csv --top 5 --quiet
python scripts/stats_summary.py 다른파일.csv               # 어떤 CSV든 범용 요약
```

- 표준 라이브러리만 사용 (pandas 불필요), UTF-8/CP949 자동 인식
- 모든 CSV: 열 유형 자동 판별, 결측치, 평균·중앙값·사분위·상위10%, IQR 이상치
- 청렴신고 CSV: 유형·상태·지역·신고자별 건수, 유형×상태 교차표, 종결률, 처리기간, 장기 처리·고액 사건, 상태-조치결과 불일치 점검
- 청렴교육 CSV: 이수율 분포, 기관유형별 평균, 우수기관 비교, 60% 미만 기관, 결측·기관명 불일치 점검

데이터 갱신 절차: `data/`의 CSV를 교체 → 커밋(또는 재배포) → 빌드가 JSON과 RSS 사본을 자동으로 다시 만듭니다.
