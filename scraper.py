"""
Scraper for HKMA and SFC regulatory announcements.
Fetches latest news and generates a static HTML page.
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HK_TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

CATEGORY_LABELS = {
    "press_release": "新闻稿",
    "circular": "通告",
    "consultation": "咨询文件",
    "speech": "演讲",
    "announcement": "公告",
    "enforcement": "执法行动",
    "other": "其他",
}


def fetch(url, timeout=20):
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


def scrape_hkma():
    """Scrape HKMA press releases and circulars."""
    items = []

    # Press releases
    try:
        url = "https://www.hkma.gov.hk/eng/news-and-media/press-releases/"
        soup = BeautifulSoup(fetch(url).text, "html.parser")
        for row in soup.select("div.nwsLst__item, li.press-release-item, .news-list-item")[:20]:
            title_el = row.select_one("a, h3, .title")
            date_el = row.select_one(".date, time, .nwsLst__date")
            if not title_el:
                continue
            link = title_el.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.hkma.gov.hk" + link
            items.append({
                "source": "HKMA",
                "category": "press_release",
                "title": title_el.get_text(strip=True),
                "date": date_el.get_text(strip=True) if date_el else "",
                "url": link,
            })
    except Exception as e:
        print(f"[HKMA press releases] {e}")

    # Circulars
    try:
        url = "https://www.hkma.gov.hk/eng/regulatory-resources/circulars/"
        soup = BeautifulSoup(fetch(url).text, "html.parser")
        for row in soup.select("div.nwsLst__item, li.circular-item, .circular-list-item")[:10]:
            title_el = row.select_one("a, h3, .title")
            date_el = row.select_one(".date, time, .nwsLst__date")
            if not title_el:
                continue
            link = title_el.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.hkma.gov.hk" + link
            items.append({
                "source": "HKMA",
                "category": "circular",
                "title": title_el.get_text(strip=True),
                "date": date_el.get_text(strip=True) if date_el else "",
                "url": link,
            })
    except Exception as e:
        print(f"[HKMA circulars] {e}")

    return items


def scrape_sfc():
    """Scrape SFC regulatory announcements and enforcement actions."""
    items = []

    endpoints = [
        (
            "https://www.sfc.hk/en/News-and-announcements/Regulatory-announcements",
            "announcement",
        ),
        (
            "https://www.sfc.hk/en/News-and-announcements/SFC-news",
            "press_release",
        ),
        (
            "https://www.sfc.hk/en/Enforcement/Disciplinary-actions-and-other-actions",
            "enforcement",
        ),
    ]

    for url, category in endpoints:
        try:
            soup = BeautifulSoup(fetch(url).text, "html.parser")
            # SFC uses various list structures; try common selectors
            rows = (
                soup.select("div.announcement-item")
                or soup.select("li.news-item")
                or soup.select("tr.announcement-row")
                or soup.select(".search-result-item")
                or soup.select("article")
            )
            for row in rows[:15]:
                title_el = row.select_one("a, h3, h4, .title, .headline")
                date_el = row.select_one(".date, time, .news-date, td.date")
                if not title_el:
                    continue
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://www.sfc.hk" + link
                items.append({
                    "source": "SFC",
                    "category": category,
                    "title": title_el.get_text(strip=True),
                    "date": date_el.get_text(strip=True) if date_el else "",
                    "url": link,
                })
        except Exception as e:
            print(f"[SFC {category}] {e}")

    return items


def scrape_hkma_rss():
    """Try HKMA RSS feed as fallback."""
    items = []
    try:
        import xml.etree.ElementTree as ET
        url = "https://www.hkma.gov.hk/eng/rss/press-releases.xml"
        root = ET.fromstring(fetch(url).text)
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            if title:
                items.append({
                    "source": "HKMA",
                    "category": "press_release",
                    "title": title,
                    "date": pub_date,
                    "url": link,
                })
    except Exception as e:
        print(f"[HKMA RSS] {e}")
    return items


def normalize_date(raw: str) -> str:
    """Try to parse and reformat date strings."""
    raw = raw.strip()
    for fmt in (
        "%d %B %Y", "%B %d, %Y", "%Y-%m-%d",
        "%d/%m/%Y", "%d-%m-%Y",
        "%a, %d %b %Y %H:%M:%S %z",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Extract date-like patterns from string
    m = re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", raw)
    if m:
        return m.group().replace("/", "-")
    return raw


def build_html(items: list, updated_at: str) -> str:
    source_filter_btns = ""
    cat_filter_btns = ""

    sources = sorted({i["source"] for i in items})
    cats = sorted({i["category"] for i in items})

    for s in sources:
        source_filter_btns += (
            f'<button class="filter-btn active" data-filter="source" data-value="{s}">{s}</button>\n'
        )
    for c in cats:
        label = CATEGORY_LABELS.get(c, c)
        cat_filter_btns += (
            f'<button class="filter-btn active" data-filter="category" data-value="{c}">{label}</button>\n'
        )

    rows_html = ""
    for item in items:
        cat_label = CATEGORY_LABELS.get(item["category"], item["category"])
        date_display = normalize_date(item["date"]) if item["date"] else "—"
        url = item["url"] or "#"
        title_html = (
            f'<a href="{url}" target="_blank" rel="noopener">{item["title"]}</a>'
            if url != "#"
            else item["title"]
        )
        rows_html += f"""
        <tr data-source="{item['source']}" data-category="{item['category']}">
          <td class="td-date">{date_display}</td>
          <td class="td-source badge-{item['source'].lower()}">{item['source']}</td>
          <td class="td-cat">{cat_label}</td>
          <td class="td-title">{title_html}</td>
        </tr>"""

    total = len(items)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>香港监管动态 | HKMA & SFC</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            background: #f5f7fa; color: #1a1a2e; min-height: 100vh; }}
    header {{ background: linear-gradient(135deg, #0f3460 0%, #16213e 100%);
              color: #fff; padding: 2rem; text-align: center; }}
    header h1 {{ font-size: 1.8rem; font-weight: 700; letter-spacing: .02em; }}
    header p {{ margin-top: .4rem; opacity: .75; font-size: .9rem; }}
    .meta {{ text-align: right; padding: .5rem 2rem; font-size: .8rem; color: #666; background: #fff;
             border-bottom: 1px solid #e2e8f0; }}
    .controls {{ padding: 1rem 2rem; background: #fff; border-bottom: 1px solid #e2e8f0;
                 display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }}
    .controls label {{ font-weight: 600; font-size: .85rem; color: #555; margin-right: .25rem; }}
    .filter-btn {{ padding: .3rem .75rem; border-radius: 999px; border: 1.5px solid #cbd5e1;
                   background: #f1f5f9; cursor: pointer; font-size: .8rem; transition: all .15s; }}
    .filter-btn.active {{ background: #0f3460; color: #fff; border-color: #0f3460; }}
    .filter-btn:hover {{ border-color: #0f3460; }}
    .search-box {{ margin-left: auto; padding: .35rem .75rem; border: 1.5px solid #cbd5e1;
                   border-radius: 8px; font-size: .85rem; width: 220px; }}
    .search-box:focus {{ outline: none; border-color: #0f3460; }}
    .stats {{ padding: .5rem 2rem; font-size: .82rem; color: #64748b; background: #f8fafc; }}
    .table-wrap {{ padding: 1rem 2rem 3rem; overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff;
             border-radius: 12px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    th {{ background: #1e3a5f; color: #fff; padding: .75rem 1rem; text-align: left;
          font-size: .82rem; font-weight: 600; letter-spacing: .03em; white-space: nowrap; }}
    td {{ padding: .65rem 1rem; font-size: .85rem; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: #f8faff; }}
    .td-date {{ white-space: nowrap; color: #64748b; font-variant-numeric: tabular-nums; }}
    .td-source {{ font-weight: 700; font-size: .75rem; border-radius: 4px; width: 60px;
                  text-align: center; padding: .3rem .5rem; }}
    .badge-hkma {{ background: #dbeafe; color: #1d4ed8; }}
    .badge-sfc  {{ background: #dcfce7; color: #166534; }}
    .td-cat  {{ color: #6b7280; font-size: .78rem; white-space: nowrap; }}
    .td-title a {{ color: #1e3a5f; text-decoration: none; line-height: 1.5; }}
    .td-title a:hover {{ text-decoration: underline; color: #2563eb; }}
    .hidden {{ display: none !important; }}
    .empty-msg {{ text-align: center; padding: 3rem; color: #94a3b8; font-size: .9rem; }}
    @media (max-width: 640px) {{
      .table-wrap {{ padding: .5rem; }}
      header h1 {{ font-size: 1.3rem; }}
      .controls {{ padding: .75rem; }}
      .search-box {{ width: 100%; margin-left: 0; }}
    }}
  </style>
</head>
<body>
<header>
  <h1>香港监管动态</h1>
  <p>金融管理局（HKMA）&nbsp;|&nbsp;证券及期货事务监察委员会（SFC）</p>
</header>

<div class="meta">数据更新时间：{updated_at}（香港时间）</div>

<div class="controls">
  <label>来源：</label>
  {source_filter_btns}
  &nbsp;
  <label>类别：</label>
  {cat_filter_btns}
  <input class="search-box" type="text" id="searchBox" placeholder="搜索关键词…">
</div>

<div class="stats" id="statsBar">共 {total} 条公告</div>

<div class="table-wrap">
  <table id="mainTable">
    <thead>
      <tr>
        <th>日期</th><th>来源</th><th>类别</th><th>标题</th>
      </tr>
    </thead>
    <tbody id="tableBody">
      {rows_html}
    </tbody>
  </table>
  <p class="empty-msg hidden" id="emptyMsg">没有符合条件的公告</p>
</div>

<script>
  const activeFilters = {{ source: new Set({json.dumps(sources)}), category: new Set({json.dumps(cats)}) }};

  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const {{ filter, value }} = btn.dataset;
      if (activeFilters[filter].has(value)) {{
        if (activeFilters[filter].size > 1) {{
          activeFilters[filter].delete(value);
          btn.classList.remove('active');
        }}
      }} else {{
        activeFilters[filter].add(value);
        btn.classList.add('active');
      }}
      applyFilters();
    }});
  }});

  document.getElementById('searchBox').addEventListener('input', applyFilters);

  function applyFilters() {{
    const q = document.getElementById('searchBox').value.toLowerCase();
    let visible = 0;
    document.querySelectorAll('#tableBody tr').forEach(row => {{
      const srcOk = activeFilters.source.has(row.dataset.source);
      const catOk = activeFilters.category.has(row.dataset.category);
      const textOk = !q || row.textContent.toLowerCase().includes(q);
      if (srcOk && catOk && textOk) {{ row.classList.remove('hidden'); visible++; }}
      else {{ row.classList.add('hidden'); }}
    }});
    document.getElementById('statsBar').textContent = `显示 ${{visible}} / {total} 条公告`;
    document.getElementById('emptyMsg').classList.toggle('hidden', visible > 0);
  }}
</script>
</body>
</html>
"""


def main():
    print("开始抓取 HKMA 数据…")
    hkma_items = scrape_hkma()
    if not hkma_items:
        print("HTML 抓取无结果，尝试 RSS…")
        hkma_items = scrape_hkma_rss()

    print(f"HKMA: {len(hkma_items)} 条")

    print("开始抓取 SFC 数据…")
    sfc_items = scrape_sfc()
    print(f"SFC: {len(sfc_items)} 条")

    all_items = hkma_items + sfc_items

    # Sort by date descending (best-effort)
    def sort_key(item):
        d = normalize_date(item.get("date", ""))
        return d if re.match(r"\d{4}-\d{2}-\d{2}", d) else "0000-00-00"

    all_items.sort(key=sort_key, reverse=True)

    now_hk = datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M")
    html = build_html(all_items, now_hk)

    out_dir = Path(__file__).parent / "docs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    # Also save raw data for debugging
    (out_dir / "data.json").write_text(
        json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"已生成 docs/index.html（共 {len(all_items)} 条）")


if __name__ == "__main__":
    main()
