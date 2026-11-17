"""Archive public market headlines with the time each was first seen (read only, no login, no order).

Fetches the public RSS feeds of five Indian business publishers and appends new items to
<data_repo>/news/YYYY-MM.csv. Only the headline, link, the publisher's own publish time, the source
and the time we first saw it are kept: no article text. The "first seen" time is what makes the
archive usable for a test, because old news cannot be rebuilt faithfully later. Run every 30 minutes
by a Windows task, or by hand. Private use only; do not publish the files.

Usage: uv run python scripts/algo_backtest/archive_news.py <data_repo>
Exit 0 if at least one feed answered, 1 if none did.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

import httpx
from defusedxml import ElementTree

FEEDS = {
    "economic_times_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "moneycontrol_market_reports": "https://www.moneycontrol.com/rss/marketreports.xml",
    "livemint_markets": "https://www.livemint.com/rss/markets",
    "business_standard_markets": "https://www.business-standard.com/rss/markets-106.rss",
    "businessline_markets": "https://www.thehindubusinessline.com/markets/feeder/default.rss",
}
COLUMNS = ["first_seen", "source", "published", "title", "link"]
AGENT = "Mozilla/5.0 (compatible; personal research reader)"


def parse(xml_text: str) -> list[tuple[str, str, str]]:
    """(title, link, published) for each item in an RSS document; broken items are skipped."""
    out = []
    root = ElementTree.fromstring(xml_text)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            out.append((title, link, (item.findtext("pubDate") or "").strip()))
    return out


def new_rows(items, source: str, seen: set[str], now: datetime) -> list[dict]:
    rows = []
    for title, link, published in items:
        if link in seen:
            continue
        seen.add(link)
        rows.append(
            {
                "first_seen": now.isoformat(timespec="seconds"),
                "source": source,
                "published": published,
                "title": title,
                "link": link,
            }
        )
    return rows


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    out_dir = Path(sys.argv[1]) / "news"
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    target = out_dir / f"{now:%Y-%m}.csv"
    seen: set[str] = set()
    if target.exists():
        with target.open(encoding="utf-8", newline="") as handle:
            seen = {r["link"] for r in csv.DictReader(handle)}
    added, answered = 0, 0
    fresh = not target.exists()
    with (
        httpx.Client(timeout=20, headers={"User-Agent": AGENT}, follow_redirects=True) as http,
        target.open("a", encoding="utf-8", newline="") as handle,
    ):
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if fresh:
            writer.writeheader()
        for source, url in FEEDS.items():
            try:
                items = parse(http.get(url).text)
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as why:
                print(f"{source}: skipped ({type(why).__name__})")
                continue
            answered += 1
            rows = new_rows(items, source, seen, now)
            writer.writerows(rows)
            added += len(rows)
    print(
        f"{now:%Y-%m-%d %H:%M}: {answered} of {len(FEEDS)} feeds answered, {added} new headlines."
    )
    return 0 if answered else 1


if __name__ == "__main__":
    raise SystemExit(main())
