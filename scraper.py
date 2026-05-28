import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

HK_TZ = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
}
CATEGORIES = {
    "press_release": "新闻稿",
    "circular": "通告",
    "announcement": "公告",
    "enforcement": "执法行动",
}


def fetch(url):
    return requests.get(url, headers=HEADERS, timeout=20)


def scrape_hkma():
    items = []
    try:
        import xml.etree.ElementTree as ET
        r = fetch("https://www.hkma.gov.hk/eng/rss/press-releases.xml")
        root = ET.fromstring(r.text)
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            date = item.findtext("pubDate", "").strip()
            if title:
                items.append({
                    "source": "HKMA",
                    "category": "press_release",
                    "title": title,
                    "date": date,
                    "url": link,
                })
    except Exception as e:
        print(f"HKMA RSS error: {e}")
    if not items:
        try:
            soup = BeautifulSoup(
                fetch("https://www.hkma.gov.hk/eng/news-and-media/press-releases/").text,
                "html.parser",
            )
            for a in soup.select("a")[:30]:
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "press-release" in href and len(text) > 20:
                    if not href.startswith("http"):
                        href = "https://www.hkma.gov.hk" + href
                    items.append({
                        "source": "HKMA",
                        "category": "press_release",
                        "title": text,
                        "date": "",
                        "url": href,
                    })
        except Exception as e:
            print(f"HKMA HTML error: {e}")
    return items


def scrape_sfc():
    items = []
    urls = [
        ("https://www.sfc.hk/en/News-and-announcements/Regulatory-announcements", "announcement"),
        ("https://www.sfc.hk/en/News-and-announcements/SFC-news", "press_release"),
        ("https://www.sfc.hk/en/Enforcement/Disciplinary-actions-and-other-actions", "enforcement"),
    ]
    for url, cat in urls:
        try:
            soup = BeautifulSoup(fetch(url).text, "html.parser")
            count = 0
            for a in soup.select("a"):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if len(text) > 20 and any(
                    k in href for k in ("announcement", "news", "enforcement", "circular")
                ):
                    if not href.startswith("http"):
                        href = "https://www.sfc.hk" + href
                    items.append({
                        "source": "SFC",
                        "category": cat,
                        "title": text,
                        "date": "",
                        "url": href,
                    })
                    count += 1
                    if count >= 15:
                        break
        except Exception as e:
            print(f"SFC {cat} error: {e}")
    return items


def normalize_date(raw):
    raw = raw.strip()
    for fmt in (
        "%d %B %Y", "%B %d, %Y", "%Y-%m-%d", "%d/%m/%Y",
        "%a, %d %b %Y %H:%M:%S %z", "%d %b %Y",
    ):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", raw)
    return m.group().replace("/", "-") if m else raw


def build_html(items, updated_at):
    sources = sorted({i["source"] for i in items})
    cats = sorted({i["category"] for i in items})
    src_btns = "".join(
        f'<button class="fb active" data-f="source" data-v="{s}">{s}</button>'
        for s in sources
    )
    cat_btns = "".join(
        f'<button class="fb active" data-f="category" data-v="{c}">{CATEGORIES.get(c, c)}</button>'
        for c in cats
    )
    rows = ""
    for item in items:
        d = normalize_date(item["date"]) if item["date"] else ""
        url = item["url"] or "#"
        title = (
            f'<a href="{url}" target="_blank" rel="noopener">{item["title"]}</a>'
            if url != "#"
            else item["title"]
        )
        rows += (
            f'<tr data-source="{item["source"]}" data-category="{item["category"]}">'
            f"<td>{d}</td>"
            f'<td class="s-{item["source"].lower()}">{item["source"]}</td>'
            f"<td>{CATEGORIES.get(item['category'], item['category'])}</td>"
            f"<td>{title}</td></tr>"
        )

    sources_json = json.dumps(sources)
    cats_json = json.dumps(cats)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hong Kong Regulatory Updates</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f5f7fa;color:#1a1a2e}}
header{{background:linear-gradient(135deg,#0f3460,#16213e);color:#fff;padding:2rem;text-align:center}}
header h1{{font-size:1.8rem}}
header p{{opacity:.75;font-size:.9rem;margin-top:.4rem}}
.meta{{text-align:right;padding:.5rem 2rem;font-size:.8rem;color:#666;background:#fff;border-bottom:1px solid #e2e8f0}}
.ctrl{{padding:1rem 2rem;background:#fff;border-bottom:1px solid #e2e8f0;display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}}
.fb{{padding:.3rem .75rem;border-radius:999px;border:1.5px solid #cbd5e1;background:#f1f5f9;cursor:pointer;font-size:.8rem}}
.fb.active{{background:#0f3460;color:#fff;border-color:#0f3460}}
input{{margin-left:auto;padding:.35rem .75rem;border:1.5px solid #cbd5e1;border-radius:8px;font-size:.85rem;width:220px}}
.wrap{{padding:1rem 2rem 3rem;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
th{{background:#1e3a5f;color:#fff;padding:.75rem 1rem;text-align:left;font-size:.82rem}}
td{{padding:.65rem 1rem;font-size:.85rem;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#f8faff}}
.s-hkma{{background:#dbeafe;color:#1d4ed8;font-weight:700;font-size:.75rem;border-radius:4px;text-align:center;white-space:nowrap}}
.s-sfc{{background:#dcfce7;color:#166534;font-weight:700;font-size:.75rem;border-radius:4px;text-align:center;white-space:nowrap}}
a{{color:#1e3a5f;text-decoration:none;line-height:1.5}}
a:hover{{text-decoration:underline;color:#2563eb}}
.hidden{{display:none!important}}
</style>
</head>
<body>
<header>
<h1>Hong Kong Regulatory Updates</h1>
<p>HKMA (Hong Kong Monetary Authority) | SFC (Securities and Futures Commission)</p>
</header>
<div class="meta">Updated: {updated_at} HKT</div>
<div class="ctrl">
<span style="font-size:.85rem;font-weight:600">Source:</span>{src_btns}
&nbsp;<span style="font-size:.85rem;font-weight:600">Category:</span>{cat_btns}
<input type="text" id="q" placeholder="Search...">
</div>
<div class="wrap">
<table>
<thead><tr><th>Date</th><th>Source</th><th>Category</th><th>Title</th></tr></thead>
<tbody id="tb">{rows}</tbody>
</table>
</div>
<script>
var af={{source:new Set({sources_json}),category:new Set({cats_json})}};
document.querySelectorAll('.fb').forEach(function(b){{
  b.addEventListener('click',function(){{
    var f=b.dataset.f,v=b.dataset.v;
    if(af[f].has(v)){{if(af[f].size>1){{af[f].delete(v);b.classList.remove('active')}}}}
    else{{af[f].add(v);b.classList.add('active')}}
    run();
  }});
}});
document.getElementById('q').addEventListener('input',run);
function run(){{
  var q=document.getElementById('q').value.toLowerCase();
  document.querySelectorAll('#tb tr').forEach(function(r){{
    var ok=af.source.has(r.dataset.source)&&af.category.has(r.dataset.category)&&(!q||r.textContent.toLowerCase().indexOf(q)>=0);
    r.classList.toggle('hidden',!ok);
  }});
}}
</script>
</body>
</html>"""


def main():
    print("Fetching HKMA...")
    hkma = scrape_hkma()
    print(f"HKMA: {len(hkma)} items")
    print("Fetching SFC...")
    sfc = scrape_sfc()
    print(f"SFC: {len(sfc)} items")
    items = hkma + sfc

    def sk(i):
        d = normalize_date(i.get("date", ""))
        return d if re.match(r"\d{4}-\d{2}-\d{2}", d) else "0000-00-00"

    items.sort(key=sk, reverse=True)
    now = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M")
    html = build_html(items, now)
    out = Path(__file__).parent / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "data.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Done: {len(items)} total items")


if __name__ == "__main__":
    main()
