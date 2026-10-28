// RSS(XML) 바이트 → [{title, link, date}] (Netlify·Vercel 공용, 의존성 없음)
// 밑줄(_)로 시작하므로 Vercel에서 API 경로로 노출되지 않습니다.

function decode(bytes) {
  const head = new TextDecoder("ascii").decode(bytes.slice(0, 200));
  const m = head.match(/encoding=["']([\w-]+)["']/i);
  let enc = (m ? m[1] : "utf-8").toLowerCase();
  if (enc === "ks_c_5601-1987") enc = "euc-kr";
  try { return new TextDecoder(enc).decode(bytes); } catch { return new TextDecoder("utf-8").decode(bytes); }
}

const tag = (block, name) => {
  const m = block.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`, "i"));
  if (!m) return "";
  return m[1].replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&")
    .trim();
};

function normDate(s) {
  if (!s) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(s.trim())) return s.trim();
  const d = new Date(s);
  if (!isNaN(d)) {
    const k = new Date(d.getTime() + 9 * 3600e3); // KST
    return k.toISOString().slice(0, 16).replace("T", " ");
  }
  const m = s.match(/(\d{4})[-./](\d{1,2})[-./](\d{1,2})/);
  return m ? `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}` : s;
}

export function parseRss(bytes) {
  const xml = decode(bytes);
  const items = [];
  for (const m of xml.matchAll(/<item[\s>][\s\S]*?<\/item>/gi)) {
    const b = m[0];
    const title = tag(b, "title"), link = tag(b, "link");
    if (title && link) items.push({ title, link, date: normDate(tag(b, "pubDate") || tag(b, "dc:date")) });
  }
  return items;
}
