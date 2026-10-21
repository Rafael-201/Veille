import urllib.request, feedparser
UA = "Mozilla/5.0 (compatible; VeillePerso/1.0; lecteur RSS personnel)"
urls = {
 "fool-1": "https://www.fool.com/a/feeds/partner/googlechromefollow?apikey=5d8f8b1e-8e0e-4b6e-9a7c-2a9b3b2c1d0e",
 "fool-2": "https://www.fool.com/feeds/index.aspx?id=foolwatch&format=rss2",
 "fool-3": "https://www.fool.com/a/feeds/foolwatch?format=rss2&id=foolwatch&apikey=foolwatch_feed",
 "fool-4": "https://www.fool.com/investing-news/rss/",
 "fool-5": "https://www.fool.com/feeds/index.aspx",
 "parisien-1": "https://feeds.leparisien.fr/leparisien/rss/economie",
 "parisien-2": "https://www.leparisien.fr/economie/rss.xml",
 "parisien-3": "https://www.leparisien.fr/arc/outboundfeeds/rss/category/economie/?outputType=xml",
 "libe-1": "https://www.liberation.fr/arc/outboundfeeds/rss-all/category/economie/?outputType=xml",
 "libe-2": "https://www.liberation.fr/arc/outboundfeeds/rss/category/economie/?outputType=xml",
 "cnbc-earnings": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
 "aktionnaire": "https://www.aktionnaire.com/feed",
}
for name, url in urls.items():
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).read()
        f = feedparser.parse(raw)
        print(f"== {name}: {len(f.entries)} entries | {url}")
        for e in f.entries[:3]:
            print("   -", e.get("published", "")[:22], "|", e.get("title", "")[:90], "|", e.get("link", "")[:70])
    except Exception as ex:
        print(f"== {name}: ERROR {ex} | {url}")
