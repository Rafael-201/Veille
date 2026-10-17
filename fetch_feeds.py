#!/usr/bin/env python3
"""Récupère les flux RSS listés dans sources.json et écrit les fichiers de données du site.

Sorties (à la racine du dépôt) :
  news.json      archive des articles des 30 derniers jours, du plus récent au plus ancien
  status.json    état de chaque source (ok / erreur, nombre d'articles)
  launches.json  prochains lancements spatiaux (API Launch Library 2)

Lancement local :  pip install feedparser  puis  python fetch_feeds.py
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources.json"
DATA = ROOT  # tous les fichiers sont à la racine du dépôt

MAX_AGE_DAYS = 30        # un article reste affiché 30 jours après sa publication
MAX_PER_FEED = 3         # nouveaux articles retenus par source à chaque mise à jour
MAX_PER_DAY = 3          # et jamais plus de 3 par source pour un même jour (même si on relance à la main)
SUMMARY_CHARS = 220      # longueur max du résumé affiché
TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; VeillePerso/1.0; lecteur RSS personnel)"
LOCAL_TZ = ZoneInfo("Europe/Zurich")
LAUNCHES_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=8&mode=list"

TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
WS_RE = re.compile(r"\s+")


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, application/json, */*",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = TAG_RE.sub(" ", raw)
    text = html.unescape(html.unescape(text))  # certains flux sont doublement échappés
    return WS_RE.sub(" ", text).strip()


def shorten(text: str, limit: int = SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:.-–—")
    return cut + "…"


def entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def is_http(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


def entry_image(entry) -> str | None:
    for thumb in entry.get("media_thumbnail") or []:
        if is_http(thumb.get("url")):
            return thumb["url"]
    for media in entry.get("media_content") or []:
        kind = (media.get("type") or "") + (media.get("medium") or "")
        if is_http(media.get("url")) and ("image" in kind or not kind):
            return media["url"]
    for enc in entry.get("enclosures") or []:
        if is_http(enc.get("href")) and "image" in (enc.get("type") or ""):
            return enc["href"]
    blobs = [entry.get("summary") or ""]
    blobs += [c.get("value") or "" for c in entry.get("content") or []]
    for blob in blobs:
        match = IMG_RE.search(blob)
        if match and is_http(match.group(1)):
            return html.unescape(match.group(1))
    return None


def normalize_link(link: str) -> str:
    """Lien sans paramètres de suivi, pour repérer les doublons."""
    parts = urllib.parse.urlsplit(link)
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    return f"{parts.netloc.lower().removeprefix('www.')}{path}"


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9à-ÿ]+", " ", title.lower()).strip()


# ---------- Google News, régions, transactions, marchés ----------

def google_news_url(spec: dict) -> str:
    lang = spec.get("lang", "en")
    params = ({"hl": "fr", "gl": "FR", "ceid": "FR:fr"} if lang == "fr"
              else {"hl": "en-US", "gl": "US", "ceid": "US:en"})
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": spec["q"], **params})


def feed_url(feed: dict) -> str:
    return google_news_url(feed["google_news"]) if feed.get("google_news") else feed["url"]


def _rx(words: list[str]) -> re.Pattern:
    alts = sorted({re.escape(w.lower()) for w in words}, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(alts) + r")(?![\w-])", re.I)


HOTEL_RX = _rx([
    "hotel", "hotels", "hôtel", "hôtels", "hotelier", "hôtelier", "hôtelière", "hôtellerie", "resort", "resorts",
    "hospitality", "palace", "inn", "motel", "lodge", "lodging", "rooms", "keys", "chambres", "aparthotel",
    "marriott", "hilton", "hyatt", "accor", "ihg", "wyndham", "four seasons", "mandarin oriental", "kempinski",
    "radisson", "minor hotels", "meliá", "melia", "nh hotels", "b&b hotels", "louvre hotels", "best western",
    "choice hotels", "rosewood", "aman", "six senses", "belmond", "ennismore", "pierre & vacances", "club med",
])
DEAL_RX = re.compile(
    r"(?<![\w-])(acquires?|acquired|acquiring|acquisitions?|buys|bought|buying|sells|sold|selling|sale of|"
    r"to sell|purchases?|purchased|divests?|offloads?|snaps up|changes hands|trades hands|recapitali[sz]\w*|"
    r"takeover|merger|merges?|joint venture|refinanc\w+|portfolio deal|"
    r"acquiert|acquis|acquise|acquisition|rachète|rachètent|rachat|racheté|rachetée|cède|cèdent|cédé|cédée|cession|"
    r"vendu|vendue|vendus|achète|acheté|achetée|reprend|reprise|repris|fusion|"
    r"vend (?:l'|le |la |les |son |ses |un |deux |trois |quatre )(?:\w+ )?(?:hôtels?|établissements?|palaces?|resorts?|portefeuille))",
    re.I)
MARKET_RX = _rx([
    "stocks", "stock market", "shares", "equities", "wall street", "s&p 500", "s&p500", "nasdaq", "dow", "dow jones",
    "stoxx", "stoxx 600", "euro stoxx", "ftse", "dax", "cac 40", "cac40", "smi", "nikkei", "topix", "hang seng",
    "kospi", "sensex", "nifty", "asx", "ibovespa", "bovespa", "merval", "ipc", "tadawul", "jse", "egx30", "egx 30",
    "bourse", "bourses", "indices", "index", "yields", "treasury yields", "bond yields", "bonds", "futures",
    "marchés", "marchés financiers", "marché actions", "actions européennes", "wall street", "peso", "rand", "yen",
    "forex", "sell-off", "selloff", "rally", "bear market", "bull market",
])

REGION_WORDS = {
    "amerique-nord": [
        "united states", "états-unis", "etats-unis", "america's", "new york", "manhattan", "brooklyn", "miami",
        "florida", "floride", "california", "californie", "los angeles", "san francisco", "las vegas", "texas",
        "dallas", "houston", "austin", "chicago", "boston", "washington", "atlanta", "nashville", "orlando", "hawaii",
        "maui", "seattle", "denver", "phoenix", "new orleans", "san diego", "philadelphia", "arizona", "colorado",
        "portland", "oregon", "utah", "salt lake city", "minneapolis", "detroit", "charlotte", "carolina",
        "virginia", "georgia", "tennessee", "louisiana", "nevada", "massachusetts", "new jersey", "pennsylvania",
        "ohio", "michigan", "illinois", "san antonio", "scottsdale", "palm beach", "key west", "napa", "aspen",
        "pebblebrook", "park hotels & resorts", "host hotels", "reit", "cmbs",
        "american", "américain", "américains", "américaine", "américaines",
        "canada", "canadian", "toronto", "b.c.", "british columbia", "alberta", "ontario", "calgary", "ottawa", "montreal", "montréal", "vancouver", "quebec", "québec", "wall street",
        "s&p 500", "nasdaq", "dow", "dow jones", "federal reserve", "the fed", "treasury", "treasuries", "tsx",
    ],
    "amerique-latine": [
        "latin america", "latin american", "amérique latine", "latam", "mexico", "mexique", "mexican", "mexicain",
        "cancun", "cancún", "los cabos", "tulum", "riviera maya", "brazil", "brésil", "brazilian", "são paulo",
        "sao paulo", "rio de janeiro", "argentina", "argentine", "buenos aires", "chile", "chili", "chilean",
        "colombia", "colombie", "bogota", "bogotá", "cartagena", "peru", "pérou", "costa rica", "panama",
        "caribbean", "caraïbes", "dominican", "dominicaine", "punta cana", "puerto rico", "jamaica", "jamaïque",
        "bahamas", "aruba", "cuba", "uruguay", "ecuador", "équateur", "guatemala", "ibovespa", "bovespa", "merval",
        "peso",
    ],
    "europe": [
        "europe", "european", "européen", "européenne", "européens", "eurozone", "zone euro", "britain", "british",
        "royaume-uni", "england", "angleterre", "scotland", "écosse", "london", "londres", "ireland", "irlande",
        "edinburgh", "édimbourg", "glasgow", "manchester", "birmingham", "liverpool", "leeds", "oxford", "cambridge",
        "surrey", "kent", "sussex", "cornwall", "devon", "yorkshire", "cotswolds", "lake district", "wales",
        "pays de galles", "belfast", "caledonian",
        "dublin", "france", "français", "française", "paris", "lyon", "marseille", "cannes", "bordeaux",
        "strasbourg", "bayonne", "biarritz", "saint-jean-de-luz", "courchevel", "chamonix", "megève", "annecy",
        "germany", "allemagne", "german", "allemand", "berlin", "munich", "frankfurt", "francfort", "hamburg",
        "spain", "espagne", "spanish", "madrid", "barcelona", "barcelone", "mallorca", "majorque", "ibiza",
        "canary islands", "canaries", "italy", "italie", "italian", "rome", "milan", "venice", "venise", "florence",
        "sicily", "sicile", "sardinia", "portugal", "lisbon", "lisbonne", "porto", "algarve", "madeira", "greece",
        "grèce", "greek", "athens", "athènes", "mykonos", "santorini", "crete", "crète", "netherlands", "pays-bas",
        "dutch", "amsterdam", "belgium", "belgique", "brussels", "bruxelles", "switzerland", "suisse", "swiss",
        "zurich", "geneva", "genève", "lausanne", "gstaad", "st. moritz", "austria", "autriche", "vienna", "poland",
        "pologne", "warsaw", "czech", "prague", "hungary", "budapest", "croatia", "croatie", "dubrovnik",
        "montenegro", "denmark", "danemark", "copenhagen", "sweden", "suède", "stockholm", "norway", "norvège",
        "oslo", "finland", "helsinki", "iceland", "islande", "monaco", "luxembourg", "malta", "malte", "cyprus",
        "chypre", "turkey", "turquie", "istanbul", "stoxx", "ftse", "dax", "cac 40", "cac40", "smi", "ecb", "bce",
        "bank of england", "euronext", "bourse de paris",
    ],
    "moyen-orient": [
        "middle east", "moyen-orient", "mideast", "gulf", "golfe", "gcc", "dubai", "dubaï", "abu dhabi", "uae",
        "émirats", "emirates", "saudi", "saoudite", "riyadh", "riyad", "jeddah", "red sea", "mer rouge", "neom",
        "alula", "qatar", "doha", "oman", "muscat", "bahrain", "bahreïn", "kuwait", "koweït", "jordan", "jordanie",
        "israel", "israël", "tel aviv", "lebanon", "liban", "tadawul",
    ],
    "asie": [
        "asia", "asian", "asie", "asiatique", "asiatiques", "apac", "asia-pacific", "asie-pacifique", "japan",
        "japon", "japanese", "japonais", "tokyo", "osaka", "kyoto", "china", "chine", "chinese", "chinois",
        "beijing", "pékin", "shanghai", "shenzhen", "hong kong", "macau", "macao", "taiwan", "korea", "korean",
        "corée", "seoul", "séoul", "singapore", "singapour", "malaysia", "malaisie", "kuala lumpur", "thailand",
        "thaïlande", "bangkok", "phuket", "vietnam", "viêt nam", "hanoi", "indonesia", "indonésie", "bali",
        "jakarta", "philippines", "manila", "india", "inde", "indian", "mumbai", "delhi", "goa", "sri lanka",
        "maldives", "nepal", "cambodia", "cambodge", "australia", "australie", "australian", "sydney", "melbourne",
        "new zealand", "nouvelle-zélande", "auckland", "queenstown", "fiji", "brisbane", "perth", "gold coast", "nikkei", "topix", "hang seng", "kospi", "sensex", "nifty",
        "asx", "yen", "yuan",
    ],
    "afrique": [
        "africa", "african", "afrique", "africain", "africaine", "south africa", "afrique du sud", "johannesburg",
        "cape town", "durban", "nigeria", "lagos", "abuja", "kenya", "nairobi", "egypt", "égypte", "egyptian",
        "cairo", "le caire", "sharm el-sheikh", "hurghada", "morocco", "maroc", "marrakech", "casablanca", "rabat",
        "tangier", "tanger", "agadir", "tunisia", "tunisie", "tunis", "algeria", "algérie", "senegal", "sénégal",
        "dakar", "côte d'ivoire", "ivory coast", "abidjan", "ghana", "accra", "ethiopia", "éthiopie", "tanzania",
        "tanzanie", "zanzibar", "rwanda", "kigali", "uganda", "mauritius", "île maurice", "seychelles",
        "madagascar", "namibia", "namibie", "botswana", "zambia", "zimbabwe", "mozambique", "jse", "egx30",
        "egx 30", "rand", "naira",
    ],
}
REGION_RX = {rid: _rx(words) for rid, words in REGION_WORDS.items()}
# sigles en majuscules uniquement (« us » ou « eu » seraient ambigus en minuscules)
CASE_RX = {
    "amerique-nord": [re.compile(r"(?<![\w.])(U\.S\.|US|USA|U\.S)(?![\w])")],
    # sigles (sensibles à la casse) + devises : £ (Royaume-Uni), ₹ / crore / lakh (Inde), R$ (Brésil)
    "europe": [re.compile(r"(?<![\w.])(EU|UE|UK|U\.K\.)(?![\w])"),
               re.compile(r"£|(?<![\w-])(multi-?million-pound|million-pound)(?![\w-])", re.I)],
    "asie": [re.compile(r"₹|(?<![\w-])(crore|lakh)(?![\w-])", re.I)],
    "amerique-latine": [re.compile(r"R\$")],
}


def classify_region(text: str) -> str | None:
    """Région la plus citée dans le texte (titre de préférence). None si aucune."""
    best, best_score, best_pos = None, 0, 10 ** 9
    for rid in REGION_WORDS:
        hits = [m.start() for m in REGION_RX[rid].finditer(text)]
        for crx in CASE_RX.get(rid, []):
            hits += [m.start() for m in crx.finditer(text)]
        if not hits:
            continue
        score, pos = len(hits), min(hits)
        if score > best_score or (score == best_score and pos < best_pos):
            best, best_score, best_pos = rid, score, pos
    return best


# rachats de logiciels / start-up du secteur : ce ne sont pas des transactions d'hôtels
NOT_HOTEL_DEAL_RX = _rx([
    "revenue management", "rms", "pms", "software", "logiciel", "logiciels", "saas", "tech", "technology",
    "start-up", "startup", "plateforme", "platform", "app", "application", "booking engine", "channel manager",
    "own shares", "its shares", "buyback", "share buyback", "rachat d'actions", "ses propres actions", "bill", "tax bill",
])


def is_deal(title: str) -> bool:
    return bool(DEAL_RX.search(title) and HOTEL_RX.search(title) and not NOT_HOTEL_DEAL_RX.search(title))


def is_market(title: str) -> bool:
    return bool(MARKET_RX.search(title))


def topic_rejects(topic: dict | None, title: str, source: str | None) -> bool:
    """Vrai si l'article ne doit pas figurer dans le bloc (filtre du bloc, éditeur ou motif exclu)."""
    if not topic:
        return False
    if topic.get("match") == "deals" and not is_deal(title):
        return True
    if topic.get("match") == "markets" and not is_market(title):
        return True
    if source and source.lower() in {x.lower() for x in topic.get("exclude_sources", [])}:
        return True
    return any(re.search(rx, title, re.I) for rx in topic.get("exclude_patterns", []))


def parse_feed(cat: dict, feed: dict, topic: dict | None = None) -> tuple[list[dict], dict]:
    url = feed_url(feed)
    status = {"name": feed["name"], "cat": cat["id"], "topic": topic["id"] if topic else None, "url": url,
              "ok": False, "count": 0, "error": None}
    try:
        parsed = feedparser.parse(fetch(url))
    except Exception as exc:  # réseau, HTTP 4xx/5xx, délai dépassé
        status["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return [], status

    if not parsed.entries:
        status["error"] = "Aucun article lu" + (f" ({parsed.bozo_exception})" if parsed.get("bozo") else "")
        status["error"] = status["error"][:200]
        return [], status

    excludes = [e.lower() for e in feed.get("exclude", [])]
    cutoff = now_utc() - timedelta(days=MAX_AGE_DAYS)
    items = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title"))
        link = (entry.get("link") or "").strip()
        if not title or not is_http(link):
            continue
        publisher = None
        if feed.get("google_news"):
            publisher = clean_text((entry.get("source") or {}).get("title")) or None
            if publisher and title.endswith(f" - {publisher}"):
                title = title[: -len(publisher) - 3].rstrip()
        if topic_rejects(topic, title, publisher):
            continue
        haystack = f"{title} {link}".lower()
        if any(word in haystack for word in excludes):
            continue
        date = entry_date(entry)
        if date and date < cutoff:
            continue
        if date and date > now_utc() + timedelta(hours=6):  # date dans le futur : on la ramène à maintenant
            date = now_utc()
        summary = "" if feed.get("google_news") else clean_text(entry.get("summary") or entry.get("description"))
        if summary.lower().startswith(title.lower()):
            summary = summary[len(title):].lstrip(" .:-–—")
        item_topic = topic["id"] if topic else None
        if not topic and cat["id"] == "hotellerie" and is_deal(title):
            item_topic = "transactions"
        elif not topic and cat["id"] == "finance" and is_market(title):
            item_topic = "marches"
        region = None
        if item_topic:
            region = classify_region(title) or (None if feed.get("google_news") else feed.get("region")) \
                or classify_region(summary) or "monde"
        items.append({
            "id": hashlib.sha1(normalize_link(link).encode()).hexdigest()[:12],
            "cat": cat["id"],
            "topic": item_topic,
            "region": region,
            "feed": feed["name"],
            "source": publisher or feed["name"],
            "lang": feed.get("lang", "en"),
            "title": title,
            "link": link,
            "date": date.isoformat().replace("+00:00", "Z") if date else None,
            "summary": shorten(summary),
            "image": entry_image(entry),
        })
    items.sort(key=lambda it: it["date"] or "", reverse=True)
    items = items[:MAX_PER_FEED]
    status.update(ok=True, count=len(items))
    return items, status


def local_day(iso: str | None) -> str:
    """Jour de publication à l'heure de Genève (AAAA-MM-JJ)."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(LOCAL_TZ).date().isoformat()
    except (AttributeError, ValueError):
        return ""


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def fetch_launches(previous: dict) -> dict:
    try:
        payload = json.loads(fetch(LAUNCHES_URL))
    except Exception as exc:
        print(f"  ! lancements : {exc}", file=sys.stderr)
        return previous or {"generated_at": None, "launches": []}
    launches = []
    for item in payload.get("results", []):
        status = item.get("status") or {}
        launches.append({
            "name": item.get("name"),
            "net": item.get("net"),
            "status": status.get("abbrev") if isinstance(status, dict) else status,
            "status_label": status.get("name") if isinstance(status, dict) else None,
            "provider": item.get("lsp_name"),
            "pad": item.get("pad"),
            "location": item.get("location"),
            "mission_type": item.get("mission_type"),
            "image": item.get("image") if is_http(item.get("image")) else None,
        })
    return {"generated_at": now_utc().isoformat().replace("+00:00", "Z"), "launches": launches}


def fetch_index(spec: dict, previous: dict | None) -> dict:
    """Dernière clôture d'un indice (Yahoo Finance), variation sur la séance et sur ~1 mois."""
    out = {"symbol": spec["symbol"], "name": spec["name"], "region": spec["region"]}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(spec['symbol'])}?range=1mo&interval=1d"
    try:
        result = json.loads(fetch(url))["chart"]["result"][0]
        meta = result["meta"]
        points = [(t, c) for t, c in zip(result.get("timestamp") or [], result["indicators"]["quote"][0].get("close") or [])
                  if c is not None]
        if not points:
            raise ValueError("aucune clôture")
        last_t, last = points[-1]
        prev = points[-2][1] if len(points) >= 2 else meta.get("previousClose") or meta.get("chartPreviousClose")
        base_month = meta.get("chartPreviousClose") or points[0][1]
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
        out.update(
            last=round(last, 2),
            change_pct=round((last / prev - 1) * 100, 2) if prev else None,
            month_pct=round((last / base_month - 1) * 100, 2) if base_month else None,
            date=datetime.fromtimestamp(last_t, tz).date().isoformat(),
            currency=meta.get("currency"),
        )
    except Exception as exc:
        print(f"  ! indice {spec['symbol']} : {exc}", file=sys.stderr)
        if previous:
            return {**previous, "stale": True}
    return out


def fetch_indices(specs: list[dict], previous: dict | None) -> dict:
    before = {i["symbol"]: i for i in (previous or {}).get("indices", [])}
    with ThreadPoolExecutor(max_workers=6) as pool:
        indices = list(pool.map(lambda sp: fetch_index(sp, before.get(sp["symbol"])), specs))
    return {"generated_at": now_utc().isoformat().replace("+00:00", "Z"), "indices": indices}


def main() -> int:
    config = load_json(SOURCES, None)
    if not config:
        print("sources.json introuvable ou invalide", file=sys.stderr)
        return 1
    DATA.mkdir(exist_ok=True)
    previous = load_json(DATA / "news.json", {"items": []})

    cats_by_id = {c["id"]: c for c in config["categories"]}
    jobs = [(cat, feed, None) for cat in config["categories"] for feed in cat["feeds"]]
    for topic in config.get("topics", []):
        jobs += [(cats_by_id[topic["cat"]], feed, topic) for feed in topic["feeds"]]
    feeds_by_name = {feed["name"]: (cat, feed, topic) for cat, feed, topic in jobs}
    started = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda job: parse_feed(*job), jobs))

    fresh, statuses = [], []
    for (cat, feed, topic), (items, status) in zip(jobs, results):
        fresh.extend(items)
        statuses.append(status)
        mark = "ok " if status["ok"] else "ERR"
        label = topic["label"] if topic else cat["label"]
        print(f"  [{mark}] {label:<12} {feed['name']:<34} {status['count']:>3}  {status['error'] or ''}")

    # Archive : on part des articles déjà enregistrés, puis on ajoute ou rafraîchit avec ceux du jour.
    # Un article disparaît seulement 30 jours après sa publication (ou si sa source est retirée de sources.json).
    stamp = now_utc().isoformat().replace("+00:00", "Z")
    merged = {}
    for it in previous.get("items", []):
        it.setdefault("feed", it.get("source"))
        if it.get("id") and it["feed"] in feeds_by_name:
            merged[it["id"]] = it
    for it in fresh:
        old = merged.get(it["id"])
        if not it["date"]:
            # article sans date : on garde la date où il a été vu pour la première fois
            it["date"] = (old or {}).get("date") or stamp
        if old:
            it["image"] = it["image"] or old.get("image")
            it["summary"] = it["summary"] or old.get("summary", "")
        merged[it["id"]] = it

    # Reclasse les articles archivés (transactions / marchés + région) avec les règles actuelles
    for key in list(merged):
        it = merged[key]
        cat, feed, topic = feeds_by_name[it["feed"]]
        if topic_rejects(topic, it["title"], it.get("source")):
            del merged[key]
            continue
        if topic:
            it["topic"] = topic["id"]
        elif cat["id"] == "hotellerie" and is_deal(it["title"]):
            it["topic"] = "transactions"
        elif cat["id"] == "finance" and is_market(it["title"]):
            it["topic"] = "marches"
        else:
            it["topic"] = None
        default_region = None if feed.get("google_news") else feed.get("region")
        it["region"] = (classify_region(it["title"]) or default_region
                        or classify_region(it.get("summary") or "") or "monde") if it["topic"] else None

    cutoff = (now_utc() - timedelta(days=MAX_AGE_DAYS)).isoformat().replace("+00:00", "Z")
    kept = [it for it in merged.values() if (it.get("date") or stamp) >= cutoff]

    seen_links, seen_titles, unique, per_day = set(), set(), [], {}
    for it in sorted(kept, key=lambda it: it["date"] or "", reverse=True):
        key_link, key_title = normalize_link(it["link"]), normalize_title(it["title"])
        if key_link in seen_links or key_title in seen_titles:
            continue
        day = local_day(it["date"])
        if per_day.get((it["feed"], day), 0) >= MAX_PER_DAY:
            continue
        per_day[(it["feed"], day)] = per_day.get((it["feed"], day), 0) + 1
        seen_links.add(key_link)
        seen_titles.add(key_title)
        unique.append(it)

    per_source = {}
    for it in unique:
        per_source[it["feed"]] = per_source.get(it["feed"], 0) + 1
    for st in statuses:
        st["archived"] = per_source.get(st["name"], 0)

    generated = now_utc().isoformat().replace("+00:00", "Z")
    categories = [{"id": c["id"], "label": c["label"]} for c in config["categories"]]
    topics = [{"id": t["id"], "cat": t["cat"], "label": t["label"], "intro": t.get("intro", "")}
              for t in config.get("topics", [])]
    (DATA / "news.json").write_text(json.dumps(
        {"generated_at": generated, "categories": categories, "topics": topics,
         "regions": config.get("regions", []), "items": unique},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (DATA / "status.json").write_text(json.dumps(
        {"generated_at": generated, "sources": statuses}, ensure_ascii=False, indent=1), encoding="utf-8")
    launches = fetch_launches(load_json(DATA / "launches.json", None))
    (DATA / "launches.json").write_text(json.dumps(launches, ensure_ascii=False, indent=1), encoding="utf-8")
    markets = fetch_indices(config.get("indices", []), load_json(DATA / "markets.json", None))
    (DATA / "markets.json").write_text(json.dumps(markets, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(s["ok"] for s in statuses)
    print(f"{len(unique)} articles en archive ({MAX_AGE_DAYS} j), {ok}/{len(statuses)} sources OK, "
          f"{len(launches['launches'])} lancements, {sum(1 for i in markets['indices'] if i.get('last'))} indices, "
          f"en {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
