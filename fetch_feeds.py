#!/usr/bin/env python3
"""Récupère les flux RSS listés dans sources.json et écrit les fichiers de données du site.

Sorties (à la racine du dépôt) :
  news.json      articles récents, triés du plus récent au plus ancien
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
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources.json"
DATA = ROOT  # tous les fichiers sont à la racine du dépôt

MAX_AGE_DAYS = 10        # on ignore les articles plus vieux
MAX_PER_FEED = 20        # articles gardés par source
SUMMARY_CHARS = 220      # longueur max du résumé affiché
TIMEOUT = 20
USER_AGENT = "Mozilla/5.0 (compatible; VeillePerso/1.0; lecteur RSS personnel)"
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


def parse_feed(cat: dict, feed: dict) -> tuple[list[dict], dict]:
    status = {"name": feed["name"], "cat": cat["id"], "url": feed["url"], "ok": False, "count": 0, "error": None}
    try:
        parsed = feedparser.parse(fetch(feed["url"]))
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
        haystack = f"{title} {link}".lower()
        if any(word in haystack for word in excludes):
            continue
        date = entry_date(entry)
        if date and date < cutoff:
            continue
        if date and date > now_utc() + timedelta(hours=6):  # date dans le futur : on la ramène à maintenant
            date = now_utc()
        summary = clean_text(entry.get("summary") or entry.get("description"))
        if summary.lower().startswith(title.lower()):
            summary = summary[len(title):].lstrip(" .:-–—")
        items.append({
            "id": hashlib.sha1(normalize_link(link).encode()).hexdigest()[:12],
            "cat": cat["id"],
            "source": feed["name"],
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


def main() -> int:
    config = load_json(SOURCES, None)
    if not config:
        print("sources.json introuvable ou invalide", file=sys.stderr)
        return 1
    DATA.mkdir(exist_ok=True)
    previous = load_json(DATA / "news.json", {"items": []})
    previous_by_source = {}
    for it in previous.get("items", []):
        previous_by_source.setdefault(it.get("source"), []).append(it)

    jobs = [(cat, feed) for cat in config["categories"] for feed in cat["feeds"]]
    started = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda job: parse_feed(*job), jobs))

    cutoff = (now_utc() - timedelta(days=MAX_AGE_DAYS)).isoformat()
    all_items, statuses = [], []
    for (cat, feed), (items, status) in zip(jobs, results):
        if not status["ok"]:
            # source en panne : on garde ses articles de la dernière mise à jour réussie
            kept = [it for it in previous_by_source.get(feed["name"], []) if (it.get("date") or "") >= cutoff]
            items = kept
            status["kept_previous"] = len(kept)
        all_items.extend(items)
        statuses.append(status)
        mark = "ok " if status["ok"] else "ERR"
        print(f"  [{mark}] {cat['label']:<11} {feed['name']:<20} {status['count']:>3}  {status['error'] or ''}")

    # article sans date : on garde la date où il a été vu pour la première fois
    first_seen = {it["id"]: it.get("date") for it in previous.get("items", [])}
    stamp = now_utc().isoformat().replace("+00:00", "Z")
    for it in all_items:
        if not it["date"]:
            it["date"] = first_seen.get(it["id"]) or stamp

    seen_links, seen_titles, unique = set(), set(), []
    for it in sorted(all_items, key=lambda it: it["date"] or "", reverse=True):
        key_link, key_title = normalize_link(it["link"]), normalize_title(it["title"])
        if key_link in seen_links or key_title in seen_titles:
            continue
        seen_links.add(key_link)
        seen_titles.add(key_title)
        unique.append(it)

    generated = now_utc().isoformat().replace("+00:00", "Z")
    categories = [{"id": c["id"], "label": c["label"]} for c in config["categories"]]
    (DATA / "news.json").write_text(json.dumps(
        {"generated_at": generated, "categories": categories, "items": unique},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "status.json").write_text(json.dumps(
        {"generated_at": generated, "sources": statuses}, ensure_ascii=False, indent=1), encoding="utf-8")
    launches = fetch_launches(load_json(DATA / "launches.json", None))
    (DATA / "launches.json").write_text(json.dumps(launches, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(s["ok"] for s in statuses)
    print(f"{len(unique)} articles, {ok}/{len(statuses)} sources OK, "
          f"{len(launches['launches'])} lancements, en {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
