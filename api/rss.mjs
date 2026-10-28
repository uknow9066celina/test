// Vercel Functions — 행정안전부 RSS 프록시 (/api/rss)
import { parseRss } from "./_rss-parse.mjs";

const FEED_URL = "https://www.mois.go.kr/gpms/view/jsp/rss/rss.jsp?ctxCd=1012";

export async function GET() {
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
}
