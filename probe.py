import json, urllib.request, urllib.parse, feedparser
UA = "Mozilla/5.0 (compatible; VeillePerso/1.0; lecteur RSS personnel)"
def get(u):
    r = urllib.request.Request(u, headers={"User-Agent": UA})
    return urllib.request.urlopen(r, timeout=20).read()
def gn(q, lang="en-US", gl="US", ceid="US:en"):
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": lang, "gl": gl, "ceid": ceid})
tests = {
 "deal-mideast": gn('hotel (acquires OR acquisition OR sells OR sold OR buys) (Dubai OR Saudi OR UAE OR Qatar) when:14d'),
 "deal-europe-fr": gn('hôtel (rachat OR cession OR acquiert OR rachète OR "vend") when:14d', "fr", "FR", "FR:fr"),
 "mkt-asia": gn('(Nikkei OR "Hang Seng" OR "Asian stocks" OR Kospi) when:3d'),
 "hospitalitynet-transactions": "https://www.hospitalitynet.org/news/transactions.xml",
}
for name, url in tests.items():
    try:
        f = feedparser.parse(get(url))
        print(f"== {name}: {len(f.entries)} entries")
        for e in f.entries[:4]:
            src = (e.get("source") or {}).get("title")
            print("  -", e.get("published", "")[:22], "|", src, "|", e.title[:110], "|", e.link[:60])
    except Exception as ex:
        print(f"== {name}: ERROR {ex}")
for sym in ["^GSPC", "^STOXX50E", "^SSMI", "^N225", "^BVSP", "^TASI.SR", "^J203.JO", "^CASE30", "^MXX", "^HSI", "^FCHI", "000001.SS"]:
    for host in ["query1", "query2"]:
        try:
            d = json.loads(get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=5d&interval=1d"))
            m = d["chart"]["result"][0]["meta"]
            closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            print(f"YF {sym} via {host}: price={m.get('regularMarketPrice')} prev={m.get('chartPreviousClose')} closes={[round(c,1) if c else c for c in closes]} name={m.get('shortName') or m.get('longName')} tz={m.get('exchangeTimezoneName')}")
            break
        except Exception as ex:
            print(f"YF {sym} via {host}: ERROR {ex}")
for sym in ["^spx", "^ukx", "^dax", "^nkx"]:
    try:
        print("STOOQ", sym, get(f"https://stooq.com/q/l/?s={urllib.parse.quote(sym)}&f=sd2t2ohlcv&h&e=csv").decode()[:200].replace("\n"," / "))
    except Exception as ex:
        print("STOOQ", sym, "ERROR", ex)
