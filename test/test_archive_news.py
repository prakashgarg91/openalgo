"""The news archive keeps each link once and stores no article text."""

from datetime import datetime

from scripts.algo_backtest import archive_news as an

RSS = """<rss><channel>
<item><title>Nifty ends higher</title><link>http://a/1</link><pubDate>Tue, 17 Nov 2026 10:00:00 +0530</pubDate></item>
<item><title></title><link>http://a/2</link></item>
<item><title>No link</title></item>
</channel></rss>"""


def test_parse_skips_items_without_a_title_or_link():
    assert an.parse(RSS) == [("Nifty ends higher", "http://a/1", "Tue, 17 Nov 2026 10:00:00 +0530")]


def test_a_link_already_seen_is_not_stored_twice():
    seen: set[str] = set()
    now = datetime(2026, 11, 17, 12, 0)
    first = an.new_rows(an.parse(RSS), "src", seen, now)
    again = an.new_rows(an.parse(RSS), "src", seen, now)
    assert len(first) == 1 and again == []
    assert set(first[0]) == set(an.COLUMNS)
