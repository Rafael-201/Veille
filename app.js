/* La Veille — affichage des news.
   Les données viennent de news.json, launches.json, status.json
   (générés par fetch_feeds.py) et selections.json (rempli à la main). */
(() => {
  "use strict";

  const PAGE = 40;
  const EXTRA_VIEWS = [
    { id: "selections", label: "Mes sélections" },
    { id: "alire", label: "À lire" },
  ];
  const STATUS_LABELS = {
    Go: ["Confirmé", "go"], TBC: ["À confirmer", "wait"], TBD: ["Date à confirmer", "wait"],
    Hold: ["Suspendu", "bad"], "In Flight": ["En vol", "done"], Success: ["Réussi", "done"],
    Failure: ["Échec", "bad"], "Partial Failure": ["Échec partiel", "bad"],
  };

  /* ---------- Stockage local (facultatif : le site marche sans) ---------- */
  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); }
      catch (e) { return fallback; }
    },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* stockage indisponible */ } },
  };

  const state = {
    cats: [], items: [], launches: [], selections: [], sources: [], generatedAt: null,
    q: "", lang: store.get("veille.lang", "all"), shown: PAGE,
    saved: store.get("veille.saved", []),
    lastVisit: store.get("veille.lastVisit", null),
    loaded: false, error: null,
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const viewEl = $("#view");

  /* ---------- Utilitaires ---------- */
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "#");
  const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const toDate = (iso) => (iso ? new Date(iso) : null);

  const fmtLongDate = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const fmtDay = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long" });
  const fmtTime = new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit" });
  const fmtShort = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
  const fmtLaunch = new Intl.DateTimeFormat("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit" });
  const fmtMonth = new Intl.DateTimeFormat("fr-FR", { month: "short" });
  const fmtWeekdayShort = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short" });
  const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });

  // Passé : « il y a 25 minutes », « il y a 3 heures », « hier, 18:40 », « mer. 14 oct. »
  // Futur (lancements) : « dans 5 heures », « dans 3 jours »
  function relative(date) {
    if (!date) return "";
    const sec = Math.round((date - Date.now()) / 1000);
    const abs = Math.abs(sec);
    if (sec > 0) {
      if (abs < 3600) return rtf.format(Math.max(1, Math.round(sec / 60)), "minute");
      if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
      return rtf.format(Math.round(sec / 86400), "day");
    }
    if (abs < 60) return "à l’instant";
    if (abs < 3600) return rtf.format(-Math.round(abs / 60), "minute");
    if (abs < 12 * 3600) return rtf.format(-Math.round(abs / 3600), "hour");
    const label = dayLabel(date);
    if (label === "Aujourd’hui" || label === "Hier") return `${label.toLowerCase()}, ${fmtTime.format(date)}`;
    return fmtWeekdayShort.format(date);
  }
  function dayKey(d) { return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`; }
  function dayLabel(d) {
    const today = new Date();
    const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
    if (dayKey(d) === dayKey(today)) return "Aujourd’hui";
    if (dayKey(d) === dayKey(yesterday)) return "Hier";
    return fmtDay.format(d);
  }

  const catLabel = (id) => (state.cats.find((c) => c.id === id) || {}).label || id;
  const isNew = (it) => state.lastVisit && it.date && Date.parse(it.date) > state.lastVisit;
  const isSaved = (id) => state.saved.some((s) => s.id === id);
  const findItem = (id) => state.items.find((i) => i.id === id) || state.saved.find((i) => i.id === id) || state.selections.find((i) => i.id === id);

  function matches(it) {
    if (state.lang !== "all" && it.lang !== state.lang) return false;
    if (!state.q) return true;
    const hay = fold(`${it.title} ${it.summary || ""} ${it.source} ${it.note || ""}`);
    return fold(state.q).split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
  }
  const filtered = (cat) => state.items.filter((it) => (!cat || it.cat === cat) && matches(it));

  function currentView() {
    const id = location.hash.replace(/^#/, "");
    if (state.cats.some((c) => c.id === id) || EXTRA_VIEWS.some((v) => v.id === id)) return id;
    return "une";
  }

  /* ---------- Fragments ---------- */
  const ICON_SAVE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3.5h12v17l-6-4-6 4z"/></svg>';

  function saveButton(it) {
    const on = isSaved(it.id);
    return `<button type="button" class="save" data-save="${esc(it.id)}" aria-pressed="${on}"
      aria-label="${on ? "Retirer de « À lire »" : "Garder pour plus tard"} : ${esc(it.title)}"
      title="${on ? "Retirer de « À lire »" : "Garder pour plus tard"}">${ICON_SAVE}</button>`;
  }

  function meta(it, { showCat = false, timeOnly = false } = {}) {
    const d = toDate(it.date);
    const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(it.date || "");
    const when = d && dateOnly ? `<time datetime="${esc(it.date)}">${esc(fmtShort.format(d))}</time>`
      : d ? `<time datetime="${esc(it.date)}" title="${esc(fmtLongDate.format(d))} à ${fmtTime.format(d)}">${timeOnly ? fmtTime.format(d) : relative(d)}</time>` : "";
    return `<p class="meta">
      ${showCat ? `<span class="tag">${esc(catLabel(it.cat))}</span>` : ""}
      <span class="src">${esc(it.source)}</span>
      ${when}
      ${it.lang && it.lang !== "fr" ? `<span class="lang" title="Article en anglais">${esc(it.lang.toUpperCase())}</span>` : ""}
      ${isNew(it) ? '<span class="is-new">Nouveau</span>' : ""}
    </p>`;
  }

  function story(it, opts = {}) {
    const img = it.image && !opts.noImage
      ? `<img class="thumb" src="${esc(safeUrl(it.image))}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : "";
    return `<article class="story" data-cat="${esc(it.cat)}">
      <div class="story-body">
        ${meta(it, opts)}
        <h3><a href="${esc(safeUrl(it.link))}" target="_blank" rel="noopener">${esc(it.title)}</a></h3>
        ${it.summary && !opts.noSummary ? `<p class="summary">${esc(it.summary)}</p>` : ""}
      </div>
      <div class="story-side">${img}${saveButton(it)}</div>
    </article>`;
  }

  function lead(it) {
    const media = it.image
      ? `<div class="media"><img src="${esc(safeUrl(it.image))}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></div>` : "";
    return `<article class="lead${it.image ? "" : " no-media"}" data-cat="${esc(it.cat)}">
      ${media}
      ${meta(it)}
      <h3><a href="${esc(safeUrl(it.link))}" target="_blank" rel="noopener">${esc(it.title)}</a></h3>
      ${it.summary ? `<p class="summary">${esc(it.summary)}</p>` : ""}
      ${saveButton(it)}
    </article>`;
  }

  function list(items, opts) {
    return `<ul class="list${opts && opts.compact ? " compact" : ""}">${items.map((it) => `<li>${story(it, opts)}</li>`).join("")}</ul>`;
  }

  function byDay(items, opts = {}) {
    const groups = [];
    for (const it of items) {
      const d = toDate(it.date) || new Date(0);
      const key = dayKey(d);
      let g = groups[groups.length - 1];
      if (!g || g.key !== key) { g = { key, label: it.date ? dayLabel(d) : "Sans date", items: [] }; groups.push(g); }
      g.items.push(it);
    }
    return groups.map((g) => `<section class="day" aria-label="${esc(g.label)}">
      <h3 class="day-title">${esc(g.label)}</h3>${list(g.items, { ...opts, timeOnly: true })}</section>`).join("");
  }

  function upcomingLaunches(n) {
    const limit = Date.now() - 2 * 3600 * 1000;
    return state.launches.filter((l) => l.net && Date.parse(l.net) > limit).slice(0, n);
  }

  function launchesBlock(n) {
    const items = upcomingLaunches(n);
    if (!items.length) return '<p class="small-empty">Aucun lancement à venir pour l’instant.</p>';
    return `<ul class="launches">${items.map((l) => {
      const d = new Date(l.net);
      const [rocket, mission] = String(l.name || "").split(" | ");
      const [label, kind] = STATUS_LABELS[l.status] || [l.status_label || l.status || "", "wait"];
      const place = String(l.location || "").split(",")[0];
      return `<li class="launch">
        <div class="launch-date" aria-hidden="true"><b>${d.getDate()}</b><span>${esc(fmtMonth.format(d))}</span></div>
        <div>
          <p class="launch-name">${esc(mission || rocket)}</p>
          <p class="launch-sub"><time datetime="${esc(l.net)}">${esc(fmtLaunch.format(d))} · ${esc(relative(d))}</time></p>
          <p class="launch-sub">${esc([mission ? rocket : null, l.provider, place].filter(Boolean).join(" · "))}</p>
          ${label ? `<span class="chip ${kind}">${esc(label)}</span>` : ""}
        </div>
      </li>`;
    }).join("")}</ul>`;
  }

  function pick(s) {
    return `<article class="pick" data-cat="${esc(s.cat || "selections")}">
      ${meta(s, { showCat: !!s.cat })}
      <h3><a href="${esc(safeUrl(s.link))}" target="_blank" rel="noopener">${esc(s.title)}</a></h3>
      ${s.note ? `<p class="note">${esc(s.note)}</p>` : ""}
    </article>`;
  }

  /* ---------- Vues ---------- */
  function viewFront() {
    if (state.q) return viewResults();
    const sections = state.cats.map((cat) => {
      const items = filtered(cat.id);
      let body;
      if (!items.length) {
        body = '<p class="small-empty">Rien de neuf dans cette rubrique pour le moment.</p>';
      } else {
        const top = items.slice(0, 6).find((i) => i.image) || items[0];
        const rest = items.filter((i) => i !== top).slice(0, 4);
        body = `<div class="cat-block">${lead(top)}${list(rest, { compact: true, noSummary: true, noImage: true })}</div>`;
      }
      return `<section data-cat="${esc(cat.id)}" aria-labelledby="h-${esc(cat.id)}">
        <div class="section-head"><h2 id="h-${esc(cat.id)}"><a href="#${esc(cat.id)}">${esc(cat.label)}</a></h2>
        <a class="more" href="#${esc(cat.id)}">Toute la rubrique →</a></div>${body}</section>`;
    }).join("");

    const picks = [...state.selections].sort(byDateDesc).slice(0, 3);
    const rail = `<aside class="rail" aria-label="En bref">
      <section class="panel" data-cat="spatial"><h2>Prochains lancements <a href="#spatial">Spatial →</a></h2>${launchesBlock(4)}</section>
      <section class="panel" data-cat="selections"><h2>Mes sélections <a href="#selections">Tout voir →</a></h2>
        ${picks.length ? picks.map(pick).join("") : '<p class="small-empty">Tes articles commentés apparaîtront ici.</p>'}</section>
    </aside>`;
    return `<div class="front"><div class="sections">${sections}</div>${rail}</div>`;
  }

  function viewResults() {
    const items = filtered();
    if (!items.length) return emptySearch();
    return `<div class="feed-col"><h2 class="page-title">Résultats</h2>
      <p class="page-intro">${items.length} article${items.length > 1 ? "s" : ""} pour « ${esc(state.q)} ».</p>
      ${paged(items, { showCat: true })}</div>`;
  }

  function viewCategory(id) {
    const cat = state.cats.find((c) => c.id === id);
    const items = filtered(id);
    const names = [...new Set(state.sources.filter((s) => s.cat === id).map((s) => s.name))];
    const intro = names.length ? `Sources : ${names.map(esc).join(", ")}.` : "";
    const launch = id === "spatial" && !state.q
      ? `<section class="panel launch-strip" data-cat="spatial"><h2>Prochains lancements</h2>${launchesBlock(6)}</section>` : "";
    const body = items.length ? paged(items) : (state.q || state.lang !== "all" ? emptySearch() : `<div class="empty"><h2>Rien pour l’instant</h2><p>Aucun article récent dans cette rubrique. Les flux sont relus toutes les 3 heures.</p></div>`);
    return `<div class="feed-col" data-cat="${esc(id)}"><h2 class="page-title">${esc(cat.label)}</h2>
      <p class="page-intro">${intro}</p>${launch}${body}</div>`;
  }

  function viewSelections() {
    const items = state.selections.filter(matches).sort(byDateDesc);
    if (!state.selections.length) {
      return `<div class="empty"><h2>Pas encore de sélection</h2>
        <p>Ajoute les articles qui t’ont marqué, avec ton commentaire, dans le fichier <code>selections.json</code> de ton dépôt GitHub. Le site se met à jour tout seul en une minute environ.</p>
        <p>Le mode d’emploi est dans le fichier <code>README.md</code>.</p></div>`;
    }
    if (!items.length) return emptySearch();
    return `<div class="feed-col" data-cat="selections"><h2 class="page-title">Mes sélections</h2>
      <p class="page-intro">Les articles que j’ai choisis et commentés.</p>
      <div>${items.map(pick).join("")}</div></div>`;
  }

  function viewSaved() {
    const items = [...state.saved].filter(matches);
    if (!state.saved.length) {
      return `<div class="empty"><h2>Rien de côté</h2>
        <p>Utilise le marque-page à côté d’un article pour le garder ici. La liste est enregistrée dans ce navigateur uniquement.</p>
        <p><a class="btn secondary" href="#une" style="display:inline-flex;align-items:center;text-decoration:none">Retour à la une</a></p></div>`;
    }
    if (!items.length) return emptySearch();
    return `<div class="feed-col" data-cat="alire"><h2 class="page-title">À lire</h2>
      <p class="page-intro">${state.saved.length} article${state.saved.length > 1 ? "s" : ""} gardé${state.saved.length > 1 ? "s" : ""} pour plus tard, enregistrés dans ce navigateur.</p>
      ${list(items, { showCat: true })}</div>`;
  }

  function paged(items, opts = {}) {
    const visible = items.slice(0, state.shown);
    const more = items.length > visible.length
      ? `<div class="load-more"><button type="button" class="btn secondary" data-more>Afficher plus (${items.length - visible.length} restants)</button></div>` : "";
    return byDay(visible, opts) + more;
  }

  function emptySearch() {
    const what = state.q ? `ne correspond à « ${esc(state.q)} »` : "ne correspond à ce filtre";
    return `<div class="empty"><h2>Aucun résultat</h2><p>Aucun article ${what}${state.lang !== "all" ? ` en ${state.lang === "fr" ? "français" : "anglais"}` : ""}.</p>
      <button type="button" class="btn secondary" data-clear>Effacer les filtres</button></div>`;
  }

  function viewError() {
    return `<div class="empty"><h2>Impossible de charger les news</h2>
      <p>Le fichier de données n’a pas pu être lu (${esc(state.error)}). Vérifie ta connexion, puis réessaie.</p>
      <button type="button" class="btn" data-retry>Réessayer</button></div>`;
  }

  const byDateDesc = (a, b) => (b.date || "").localeCompare(a.date || "");

  /* ---------- Rendu ---------- */
  function renderTabs() {
    const view = currentView();
    const tabs = [{ id: "une", label: "À la une" }, ...state.cats, ...EXTRA_VIEWS].map((t) => {
      let count = "";
      if (state.cats.some((c) => c.id === t.id)) {
        const n = state.items.filter((it) => it.cat === t.id && isNew(it)).length;
        if (n) count = `<span class="count" aria-label="${n} nouveaux">${n}</span>`;
      } else if (t.id === "alire" && state.saved.length) {
        count = `<span class="count neutral" aria-label="${state.saved.length} gardés">${state.saved.length}</span>`;
      }
      return `<a class="tab" data-cat="${esc(t.id)}" href="#${esc(t.id)}"${view === t.id ? ' aria-current="page"' : ""}>${esc(t.label)}${count}</a>`;
    });
    $("#tabs").innerHTML = tabs.join("");
    const current = $("#tabs [aria-current]");
    if (current) current.scrollIntoView({ block: "nearest", inline: "nearest" });
    const anyNew = state.items.some(isNew);
    $("#mark-seen").hidden = !anyNew;
  }

  function renderHeader() {
    $("#today").textContent = fmtLongDate.format(new Date());
    if (!state.generatedAt) {
      $("#updated").textContent = state.error ? "Données indisponibles" : state.loaded ? "Première mise à jour en attente" : "Chargement…";
      return;
    }
    const d = new Date(state.generatedAt);
    const ok = state.sources.filter((s) => s.ok).length;
    const late = Date.now() - d > 12 * 3600 * 1000 ? " (en retard)" : "";
    $("#updated").innerHTML = `Mis à jour <time datetime="${esc(state.generatedAt)}" title="${esc(fmtLongDate.format(d))} à ${fmtTime.format(d)}">${esc(relative(d))}</time>${late}`
      + (state.sources.length ? ` · ${ok}/${state.sources.length} sources` : "");
  }

  function renderSources() {
    $("#sources-list").innerHTML = state.sources.map((s) => `<li title="${esc(s.error || "")}">
      <span class="dot${s.ok ? "" : " err"}" aria-hidden="true"></span>
      <span><b>${esc(s.name)}</b> · ${esc(catLabel(s.cat))} · ${s.ok ? `${s.count} article${s.count > 1 ? "s" : ""}` : "en panne" + (s.kept_previous ? ` (${s.kept_previous} conservés)` : "")}</span></li>`).join("")
      || "<li>Aucune information.</li>";
  }

  function render() {
    renderHeader();
    renderTabs();
    viewEl.setAttribute("aria-busy", String(!state.loaded && !state.error));
    if (state.error) { viewEl.innerHTML = viewError(); return; }
    if (!state.loaded) return;
    const view = currentView();
    document.title = view === "une" ? "La Veille" : `${[...state.cats, ...EXTRA_VIEWS].find((v) => v.id === view).label} · La Veille`;
    viewEl.innerHTML =
      view === "une" ? viewFront()
      : view === "selections" ? viewSelections()
      : view === "alire" ? viewSaved()
      : viewCategory(view);
  }

  /* ---------- Données ---------- */
  async function getJSON(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${path} : erreur ${res.status}`);
    return res.json();
  }

  function apply({ news, launches, selections, status, previewLastVisit }) {
    if (previewLastVisit && !state.lastVisit) state.lastVisit = previewLastVisit;
    state.cats = news.categories || [];
    state.items = news.items || [];
    state.generatedAt = news.generated_at || null;
    state.launches = (launches && launches.launches) || [];
    state.sources = (status && status.sources) || [];
    state.selections = (Array.isArray(selections) ? selections : (selections && selections.items) || [])
      .filter((s) => s && s.title && s.link)
      .map((s, i) => ({ id: `sel-${i}`, source: s.source || hostOf(s.link), lang: s.lang || "fr", ...s }));
    state.loaded = true;
    state.error = null;
  }

  function hostOf(url) { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }

  async function load() {
    state.error = null;
    if (window.__VEILLE__) { apply(window.__VEILLE__); render(); renderSources(); return; }
    const [news, launches, selections, status] = await Promise.allSettled([
      getJSON("news.json"), getJSON("launches.json"), getJSON("selections.json"), getJSON("status.json"),
    ]);
    if (news.status === "rejected") {
      state.error = news.reason && news.reason.message ? news.reason.message : "erreur inconnue";
      render();
      return;
    }
    const val = (r) => (r.status === "fulfilled" ? r.value : null);
    apply({ news: news.value, launches: val(launches), selections: val(selections), status: val(status) });
    render();
    renderSources();
  }

  /* ---------- Interactions ---------- */
  function toggleSave(id) {
    const it = findItem(id);
    if (!it) return;
    if (isSaved(id)) state.saved = state.saved.filter((s) => s.id !== id);
    else state.saved = [{ ...it, savedAt: new Date().toISOString() }, ...state.saved];
    store.set("veille.saved", state.saved);
    if (currentView() === "alire") { render(); return; }
    const on = isSaved(id);
    document.querySelectorAll(`[data-save="${CSS.escape(id)}"]`).forEach((btn) => {
      btn.setAttribute("aria-pressed", String(on));
      const label = on ? "Retirer de « À lire »" : "Garder pour plus tard";
      btn.title = label;
      btn.setAttribute("aria-label", `${label} : ${it.title}`);
    });
    renderTabs();
  }

  document.addEventListener("click", (e) => {
    const save = e.target.closest("[data-save]");
    if (save) { toggleSave(save.dataset.save); return; }
    if (e.target.closest("[data-more]")) {
      state.shown += PAGE;
      const y = window.scrollY;
      render();
      window.scrollTo(0, y);
      return;
    }
    if (e.target.closest("[data-clear]")) {
      state.q = ""; $("#q").value = "";
      state.lang = "all"; store.set("veille.lang", "all");
      document.querySelector('input[name="lang"][value="all"]').checked = true;
      render();
      $("#q").focus();
      return;
    }
    if (e.target.closest("[data-retry]")) {
      state.error = null;
      viewEl.innerHTML = '<div class="skeleton" aria-hidden="true"><span></span><span></span><span></span><span></span></div>';
      load();
    }
  });

  // Image cassée : on la retire proprement
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    const leadEl = img.closest(".lead");
    if (leadEl) { leadEl.classList.add("no-media"); img.closest(".media").remove(); }
    else img.remove();
  }, true);

  let timer;
  $("#q").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = e.target.value.trim(); state.shown = PAGE; render(); }, 150);
  });

  document.querySelectorAll('input[name="lang"]').forEach((input) => {
    input.checked = input.value === state.lang;
    input.addEventListener("change", () => { state.lang = input.value; store.set("veille.lang", state.lang); state.shown = PAGE; render(); });
  });

  window.addEventListener("hashchange", () => {
    state.shown = PAGE;
    render();
    window.scrollTo(0, 0);
    $("#contenu").focus({ preventScroll: true });
  });

  $("#mark-seen").addEventListener("click", () => {
    state.lastVisit = sessionStart = Date.now();
    store.set("veille.lastVisit", state.lastVisit);
    render();
  });

  $("#theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("veille.theme", root.dataset.theme); } catch (e) { /* ignore */ }
  });

  // « Nouveau » = paru depuis ta dernière visite
  let sessionStart = Date.now();
  const rememberVisit = () => store.set("veille.lastVisit", sessionStart);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") rememberVisit(); });
  window.addEventListener("pagehide", rememberVisit);

  // Les heures relatives restent justes si l'onglet reste ouvert
  setInterval(() => { if (state.loaded) renderHeader(); }, 60 * 1000);

  render();
  load();
})();
