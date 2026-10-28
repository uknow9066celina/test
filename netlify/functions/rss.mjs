// Netlify Functions — 행정안전부 RSS 프록시 (/api/rss)
// 브라우저 직접 호출 시 CORS로 막히는 RSS를 서버에서 받아 JSON으로 돌려줍니다.
import { parseRss } from "../../api/_rss-parse.mjs";

const FEED_URL = "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012";

export default async () => {
  try {
    const r = await fetch(FEED_URL, { headers: { "User-Agent": "Mozilla/5.0 (integrity-portal proxy)" } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const items = parseRss(new Uint8Array(await r.arrayBuffer())).slice(0, 10);
    if (items.length === 0) throw new Error("항목 없음");
    return Response.json(
      { feed: "행정안전부 보도자료", source: FEED_URL, fetchedAt: new Date().toISOString(), items },
      { headers: { "Cache-Control": "public, max-age=600, s-maxage=1800" } }
    );
  } catch (e) {
    return Response.json({ error: String(e.message || e) }, { status: 502 });
  }
};

export const config = { path: "/api/rss" };
