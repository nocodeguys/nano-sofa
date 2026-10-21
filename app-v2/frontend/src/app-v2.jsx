import React, { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/300.css";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "./styles-v2.css";
import { NS_DATA, Ic } from "./data.jsx";
import { NanoTopbar, PageIntro } from "./header.jsx";
import { Section, AdvancedSection } from "./wizard/Section.jsx";
import { BackgroundSection } from "./wizard/BackgroundSection.jsx";
import { CameraSection, CAM_PRESET_DEFAULTS } from "./wizard/CameraSection.jsx";
import { ReferencesSection } from "./wizard/ReferencesSection.jsx";
import { BeddingSection } from "./wizard/BeddingSection.jsx";
import { buildRequest, toFormData } from "./wizard/request.js";

const { COLORS, COLOR_GROUPS, COLLECTIONS, MATERIALS, CATALOG_MISSING, colorById,
        SIZES_SOFA, SIZES_BED, CAMERAS, LEGS, BACKGROUNDS, canonicalBackgroundId,
        LENSES, TIMES_OF_DAY, SHADOWS,
        SHOT_TYPES, DETAIL_REGIONS_FABRIC, DETAIL_REGIONS_CORNER,
        // Missing since the Vite build (772d16c): picking "Close-up" threw
        // ReferenceError, so the close-up shot was unreachable from the UI.
        CLOSE_REGIONS_BED, CLOSE_REGIONS_SOFA,
        CAMERA_HEIGHTS, CAMERA_YAWS, DEPTHS_OF_FIELD,
        BEDDING_PRESETS, THROW_PRESETS, TIDY_LEVELS, DENSITY_LEVELS, BED_ACCENTS } = NS_DATA;

/* ---------- error handling ---------- */
const ERR_BTN = {
  fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 7,
  border: "1px solid rgba(163,58,46,.4)", background: "rgba(163,58,46,.10)",
  color: "#A33A2E", cursor: "pointer",
};

// Normalize a failed fetch Response (+ already-parsed JSON body, which may be
// null for a non-JSON proxy 502/503 page) into a typed error object the
// ErrorCard can render. The server returns { error, error_code, detail_en,
// retryable } on every failure path (see server.py _result_error/_item_error).
function errorFromResponse(r, data) {
  if (data && (data.error || data.error_code)) {
    return {
      message: data.error || `Błąd serwera (${r.status}).`,
      code: data.error_code || "SERVER_ERROR",
      detail: data.detail_en || null,
      retryable: data.retryable != null ? !!data.retryable : r.status >= 500,
    };
  }
  // No structured body — infer from the HTTP status (e.g. a proxy 503).
  if (r.status === 503) return { message: "Serwer chwilowo niedostępny (503). Spróbuj ponownie za chwilę.", code: "MODEL_OVERLOADED", retryable: true };
  if (r.status === 429) return { message: "Zbyt wiele zapytań (429). Odczekaj chwilę i spróbuj ponownie.", code: "RATE_LIMITED", retryable: true };
  return { message: `Błąd serwera (${r.status}).`, code: "SERVER_ERROR", retryable: r.status >= 500 };
}

// fetch() itself threw — network down, CORS, or an aborted (timed-out) request.
function errorFromException(e) {
  if (e && e.name === "AbortError") {
    return { message: "Generowanie trwało zbyt długo i zostało przerwane. Spróbuj ponownie.", code: "CLIENT_TIMEOUT", retryable: true };
  }
  return { message: "Brak połączenia z serwerem. Sprawdź, czy aplikacja działa, i spróbuj ponownie.", code: "CLIENT_NETWORK", retryable: true };
}

// A local validation error raised before any request is sent.
// Download-name segment: "Aria 160", "Lincoln D 17" → "aria-160", "lincoln-d-17".
function fileSlug(...parts) {
  return parts.filter(Boolean).join("-").toLowerCase().replace(/ł/g, "l")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function mkErr(message, code = "VALIDATION") {
  return { message, code, retryable: false };
}

// Client-side ETA: the per-tier seeds come with /api/config (`eta_seed`,
// the same table cost_tracker uses), keyed by the model's `tier`. Used as the
// instant estimate AND the fallback when /api/eta is unavailable, so the
// overlay never shows a flat constant. /api/eta refines with measured history.
const _ETA_FALLBACK = { "1K": [12, 24], "2K": [20, 40], "4K": [30, 60] };
function localEta(modelObj, etaSeed, res, refs) {
  const r = (res || "1K").split(" ")[0].toUpperCase();
  const table = (etaSeed && etaSeed[modelObj?.tier]) || null;
  const seed = (table && (table[r] || table["1K"])) || _ETA_FALLBACK[r] || _ETA_FALLBACK["1K"];
  const n = refs || 0;
  return {
    p50_s: Math.round((seed[0] + 1.2 * n) * 10) / 10,
    p90_s: Math.round((seed[1] + 2 * n) * 10) / 10,
    source: "estimate", n: 0,
  };
}

// Typed error card. Accepts either a structured error object or a plain string
// (back-compat for the per-variant simple cases). Offers contextual actions:
// retry for transient failures, "fix key" for auth problems.
function ErrorCard({ info, onRetry, onFixKey, compact }) {
  if (!info) return null;
  const msg = typeof info === "string" ? { message: info } : info;
  const code = msg.code || "";
  const isAuth = code === "AUTH_INVALID_KEY" || code === "MISSING_API_KEY";
  const showRetry = msg.retryable && onRetry;
  const showFixKey = isAuth && onFixKey;
  return (
    <div style={{
      margin: compact ? "6px 0 0" : "0 0 14px 0",
      padding: compact ? "8px 10px" : "10px 14px",
      borderRadius: 10, background: "rgba(163,58,46,.08)",
      border: "1px solid rgba(163,58,46,.3)", color: "#A33A2E",
      fontSize: compact ? 11 : 13,
    }}>
      <div style={{ fontWeight: 600 }}>{msg.message}</div>
      {msg.detail && <div style={{ opacity: .65, fontSize: 11, marginTop: 3 }}>{msg.detail}</div>}
      {code === "SAFETY_NO_IMAGE" && (
        <div style={{ opacity: .8, fontSize: 11, marginTop: 3 }}>
          Wskazówka: zmień zdjęcie bazowe, prompt lub referencje.
        </div>
      )}
      {(showRetry || showFixKey) && (
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          {showRetry && <button type="button" onClick={onRetry} style={ERR_BTN}>Spróbuj ponownie</button>}
          {showFixKey && <button type="button" onClick={onFixKey} style={ERR_BTN}>Popraw klucz API</button>}
        </div>
      )}
    </div>
  );
}

/* ---------- helpers ---------- */
function LegGlyph({ id }) {
  const ink = "#3A3B37";
  const wood = "#9B7048";
  const metal = "#7A7770";
  if (id === "keep")   return <svg width="40" height="32" viewBox="0 0 40 32"><rect x="4" y="6" width="32" height="12" rx="3" fill="#E2DDD0"/><text x="20" y="28" fontSize="9" textAnchor="middle" fill={ink} fontFamily="Geist Mono">obecne</text></svg>;
  if (id === "wood")   return <svg width="40" height="32" viewBox="0 0 40 32"><rect x="4" y="6" width="32" height="12" rx="3" fill={ink}/><path d="M10 18 L8 30 M30 18 L32 30" stroke={wood} strokeWidth="2.4" strokeLinecap="round"/></svg>;
  if (id === "metal")  return <svg width="40" height="32" viewBox="0 0 40 32"><rect x="4" y="6" width="32" height="12" rx="3" fill={ink}/><path d="M10 18 L7 30 M30 18 L33 30" stroke={metal} strokeWidth="1.5" strokeLinecap="round"/></svg>;
  if (id === "block")  return <svg width="40" height="32" viewBox="0 0 40 32"><rect x="4" y="6" width="32" height="12" rx="3" fill={ink}/><rect x="7" y="18" width="6" height="10" fill={wood}/><rect x="27" y="18" width="6" height="10" fill={wood}/></svg>;
  if (id === "hidden") return <svg width="40" height="32" viewBox="0 0 40 32"><rect x="4" y="6" width="32" height="16" rx="3" fill={ink}/><rect x="6" y="22" width="28" height="6" fill="#1A1B19"/></svg>;
  if (id === "swivel") return <svg width="40" height="32" viewBox="0 0 40 32"><rect x="4" y="6" width="32" height="10" rx="3" fill={ink}/><path d="M20 16 L20 24" stroke={metal} strokeWidth="2"/><ellipse cx="20" cy="27" rx="9" ry="3" fill={metal}/></svg>;
  return null;
}

function highlightJson(s) {
  const esc = s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(
    /(&quot;[^&]*?&quot;)\s*:|(&quot;[^&]*?&quot;)|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g,
    (m, key, str, kw, num) => {
      if (key) return `<span class="jk">${key}</span>:`;
      if (str) return `<span class="js">${str}</span>`;
      if (kw)  return `<span class="jb">${kw}</span>`;
      if (num) return `<span class="jn">${num}</span>`;
      return m;
    }
  );
}

/* ============================================================ */
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "sofaWidth": 58,
  "sofaBottom": 30,
  "sofaAspect": 2.4,
  "sofaRadius": 22,
  "shadowStrength": 34,
  "stageVignette": false,
  "stageZoom": 100,
  "showFloorTag": true,
  "showVariantRail": false,
  "fabAlign": "center"
}/*EDITMODE-END*/;

const API_KEY_STORAGE = "nano-sofa-v2-api-key";
const OPENAI_KEY_STORAGE = "nano-sofa-v2-openai-key"; // Lab tab (GPT Image 2.5 direct), shared with /editorial
const OPENROUTER_KEY_STORAGE = "nano-sofa-v2-openrouter-key"; // Lab tab via OpenRouter, shared with /editorial
// lab.html mounts this same bundle with <body data-mode="lab">.
const PAGE_MODE = (typeof document !== "undefined" && document.body && document.body.dataset && document.body.dataset.mode) || "photos";
const PRESETS_STORAGE = "nano-sofa-v2-presets";
// Cross-tab render gallery (server urls + generation ids), persisted so prior
// renders survive a reload and stay pickable as Fotosesja anchors.
const GALLERY_STORAGE = "nano-sofa-v2-gallery";

// The form fields a preset captures. Deliberately a whitelist (NOT a spread of
// st) so the base image (baseFile/basePreviewUrl/uploaded/alpha — File handles
// + object URLs that can't be JSON-serialized), the reference File objects
// (envFile/refs), the API key, and `seed` are never stored. Excluding seed
// means re-applying a preset still randomizes — settings travel between images,
// the exact roll does not.
const PRESET_FIELDS = [
  "kind", "color", "colorCustom", "colorCustomHex", "mat", "matNotes", "size", "legs", "bedLegs",
  "cam", "lens", "tod", "shadow", "shot", "yaw", "height", "dof", "detailRegion",
  "bg", "bgNote", "refsLock", "preserveBaseCamera",
  "bedding", "beddingCustom", "throw", "tidy", "density", "accents", "bedNote",
  "model", "aspect", "res", "outputFormat", "outputQuality",
];

// Szybki preset → seeded structured fields. Mirrors _CAM_PRESET_TO_STRUCTURED
// in server.py (server-side fallback for legacy form posts) but adds the
// lens / DoF / detail-region that the UI also seeds on click.  Used in two
// places: the preset onClick handler (to seed st.*), and the `matchedPreset`
// memo below (to highlight the tile only while the structured fields still
// match — clicking a preset and then drifting auto-deselects the tile).

// Colour picker rows for the Warianty / Seria grids: the universal groups
// first, then each fabric collection under its own label. Label rows span
// the full grid width; picking a collection colour implies its material.
function colorGridItems() {
  const items = COLOR_GROUPS.map(c => ({ type: "color", c }));
  for (const col of COLLECTIONS) {
    if (!col.codes.length) continue;
    const matName = MATERIALS.find(m => m.id === col.material)?.name || col.material;
    items.push({ type: "label", text: `${col.name}${matName ? " · " + matName : ""}`, key: "lbl-" + col.id });
    for (const c of col.codes) items.push({ type: "color", c });
  }
  return items;
}
const COLOR_GRID_ITEMS = colorGridItems();
const GRID_LABEL_STYLE = { gridColumn: "1 / -1", fontSize: 10.5, letterSpacing: ".06em", textTransform: "uppercase",
  color: "var(--ink-3)", fontFamily: "Geist Mono", marginTop: 6 };

function CatalogMissing() {
  return (
    <div className="app-frame" style={{ display: "grid", placeItems: "center", minHeight: "100vh", padding: 24 }}>
      <div style={{ maxWidth: 520, textAlign: "center" }}>
        <h1 style={{ fontSize: 22, marginBottom: 8 }}>Nie udało się wczytać katalogu tkanin</h1>
        <p style={{ color: "var(--ink-3)", fontSize: 14, lineHeight: 1.55 }}>
          Strona nie dostała pliku <code>/catalog.js</code> z serwera. Sprawdź, czy backend działa
          (w trybie deweloperskim uruchom najpierw <code>./app-v2/run.sh</code>), a potem odśwież stronę.
        </p>
        <button className="btn" type="button" onClick={() => window.location.reload()} style={{ marginTop: 12 }}>Odśwież</button>
      </div>
    </div>
  );
}

function App({ t, mode = "photos" }) {
  // Lab mode (/lab, <body data-mode="lab">): the very same wizard, but the
  // engine is the OpenAI Images API (GPT Image 2.5) with the user's OpenAI
  // key instead of Gemini. Beds are the default subject there.
  const isLab = mode === "lab";
  const [oaKey, setOaKey] = useState(() => {
    try { return localStorage.getItem(OPENAI_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(OPENAI_KEY_STORAGE, oaKey); } catch {}
  }, [oaKey]);
  const [orKey, setOrKey] = useState(() => {
    try { return localStorage.getItem(OPENROUTER_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(OPENROUTER_KEY_STORAGE, orKey); } catch {}
  }, [orKey]);
  const [quality, setQuality] = useState("");   // Images API quality tier (Lab models)
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(API_KEY_STORAGE, apiKey); } catch {}
  }, [apiKey]);
  // Open the key field automatically on first load when no key is set.
  const [showKeyEdit, setShowKeyEdit] = useState(() => {
    try { return !(localStorage.getItem(isLab ? OPENAI_KEY_STORAGE : API_KEY_STORAGE) || ""); } catch { return true; }
  });

  // Server-driven config: models + per-model constraints (max_refs,
  // resolutions, pricing, eta seeds) from app-v2/models.json via /api/config.
  // No model id lives in this file: until the config arrives the picker is
  // empty and the POST carries model="" (the server applies its default).
  const [serverConfig, setServerConfig] = useState({ models: [], default_model: "", eta_seed: null });
  useEffect(() => {
    fetch("/api/config")
      .then(r => r.ok ? r.json() : null)
      .then(cfg => {
        if (!cfg) return;
        if (isLab) {
          if (cfg.lab_models && cfg.lab_models.length) {
            setServerConfig({ ...cfg, models: cfg.lab_models, default_model: cfg.lab_default_model || cfg.lab_models[0].id });
          }
        } else if (cfg.models && cfg.models.length) setServerConfig(cfg);
      })
      .catch(() => {});
  }, []);

  // Which materials have curated reference photos on this instance, and the
  // catalogue version this page was built from. Polled on focus + every
  // minute: an admin save elsewhere sets `catalogStale`, and the banner
  // offers a reload (no automatic reload — the form would be lost).
  const [catalogRefs, setCatalogRefs] = useState({});
  const [catalogStale, setCatalogStale] = useState(false);
  const catalogVersion = useRef(null);
  useEffect(() => {
    let cancelled = false;
    const check = () => fetch("/api/catalog-status", { cache: "no-store" })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || cancelled) return;
        if (catalogVersion.current === null) { catalogVersion.current = data.version; setCatalogRefs(data.references || {}); }
        else if (data.version !== catalogVersion.current) setCatalogStale(true);
      })
      .catch(() => {});
    check();
    const onFocus = () => { if (document.visibilityState === "visible") check(); };
    document.addEventListener("visibilitychange", onFocus);
    window.addEventListener("focus", onFocus);
    const timer = setInterval(check, 60000);
    return () => { cancelled = true; clearInterval(timer); document.removeEventListener("visibilitychange", onFocus); window.removeEventListener("focus", onFocus); };
  }, []);

  const [st, setSt] = useState({
    uploaded: false, baseFile: null, baseFileName: "", baseFileSize: 0, basePreviewUrl: null,
    kind: "bed",
    // Catalogue name of the product in the base photo (TRE-92). Identity only:
    // stamped into the render's metadata and download name, never the prompt.
    product: "",
    color: "greige", colorCustom: "", colorCustomHex: "",
    mat: "boucle", matNotes: "",
    size: "160",
    legs: "keep",
    // Beds skip legs by default (most sit on a plinth). Toggle on to render
    // visible legs — the backend already honours a non-"keep" leg for beds.
    bedLegs: false,
    // The default background (ivory) is a locked backdrop, so the camera
    // starts on its defaults: 85 mm, f/8, eye level (see pickBackground).
    cam: "studio", lens: "85mm_product", tod: "noon_neutral", shadow: "soft_diffuse",
    // Structured camera controls (section 08). When `shot` is "", the server
    // derives shot/yaw/height from the `cam` preset for back-compat. Once
    // the user touches any of these chips/selects we send explicit values.
    shot: "hero", yaw: "34_left", height: "eye", dof: "deep",
    detailRegion: "weave",
    // Background (section 01): ONE id — a studio backdrop (locked ones get
    // the catalog treatment server-side), a lifestyle scene, or "custom"
    // (bgFile is the user's photo, bgNote its optional note).
    bg: "ivory", bgFile: null, bgNote: "",
    refs: [null, null, null], refsLock: false,
    // Lock camera angle + framing + object pose to the base photo (section 02).
    // Wizard color/material/size/scene still apply — the model just keeps the
    // exact same viewpoint as the uploaded base image. Useful for detail crops
    // where any reframing would be wrong.
    preserveBaseCamera: false,
    // Bed-only styling block (section 10). Ignored for sofas.
    bedding: "linen_white", beddingCustom: "",
    throw: "none",
    tidy: "lived_in",
    density: "balanced",
    accents: [],            // array of BED_ACCENTS ids
    bedNote: "",            // optional free-text styling note
    model: "", aspect: "4:3", res: "1K", seed: "",
    outputFormat: "jpg", outputQuality: 82,
  });
  const set = patch => setSt(s => ({ ...s, ...patch }));

  // ---- Presets: save/reuse the whole config across base images ------------ //
  // Stored client-side (localStorage), same trust model as the API key — no
  // server round-trip, no shared volume. Export/import covers cross-device use.
  const [presets, setPresets] = useState(() => {
    try { return JSON.parse(localStorage.getItem(PRESETS_STORAGE) || "[]"); } catch { return []; }
  });
  useEffect(() => {
    try { localStorage.setItem(PRESETS_STORAGE, JSON.stringify(presets)); } catch {}
  }, [presets]);
  const presetFileRef = useRef(null);
  const [presetMsg, setPresetMsg] = useState("");
  const [selectedPreset, setSelectedPreset] = useState("");

  const savePreset = () => {
    const name = (window.prompt("Nazwa presetu:") || "").trim();
    if (!name) return;
    const params = Object.fromEntries(PRESET_FIELDS.map(k => [k, st[k]]));
    setPresets(p => [...p.filter(x => x.name !== name), { name, params }]);
    setPresetMsg(`Zapisano „${name}”.`);
  };
  const applyPreset = (name) => {
    const p = presets.find(x => x.name === name);
    if (!p) return;
    // Presets saved before phase 3 carry env / catalog / catalogProfile;
    // fold them into the one background id and drop the dead fields.
    const params = { ...p.params };
    if (params.bg === undefined) {
      params.bg = (params.catalog
        ? canonicalBackgroundId(params.catalogProfile)
        : canonicalBackgroundId(params.env)) || "ivory";
    }
    // Pre-phase-4 catalog presets had their camera ignored by the server
    // (85 mm, f/8, eye level were forced); apply those so they render the same.
    if (params.catalog === true) Object.assign(params, { lens: "85mm_product", dof: "deep", height: "eye" });
    for (const k of ["env", "envNote", "envMode", "catalog", "catalogProfile", "anchorRef", "alpha"]) delete params[k];
    set(params);   // merges params; base image, API key and seed untouched
    setPresetMsg(`Wczytano „${name}” — zdjęcie bazowe i seed bez zmian.`);
  };
  const deletePreset = (name) => {
    if (!name) return;
    setPresets(p => p.filter(x => x.name !== name));
    setPresetMsg(`Usunięto „${name}”.`);
  };
  const exportPresets = () => {
    try {
      const blob = new Blob([JSON.stringify(presets, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "nano-sofa-presets.json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch {}
  };
  const importPresets = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const incoming = JSON.parse(reader.result);
        if (!Array.isArray(incoming)) throw new Error("bad shape");
        const valid = incoming.filter(x => x && typeof x.name === "string" && x.params);
        // merge by name (imported wins)
        setPresets(prev => {
          const names = new Set(valid.map(x => x.name));
          return [...prev.filter(x => !names.has(x.name)), ...valid];
        });
        setPresetMsg(`Zaimportowano ${valid.length} preset(ów).`);
      } catch {
        setPresetMsg("Nie udało się wczytać pliku presetów (zły format).");
      }
    };
    reader.readAsText(file);
  };

  const fileRef = useRef(null);
  const refFileRef = useRef(null);
  const refSlotRef = useRef(-1);  // which reference slot the next file-pick fills
  const onPickBase = (file) => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    set({ baseFile: file, baseFileName: file.name, baseFileSize: file.size, basePreviewUrl: url, uploaded: true });
  };
  const onPickRef = (file) => {
    const slot = refSlotRef.current;
    refSlotRef.current = -1;
    if (!file || slot < 0) return;
    const url = URL.createObjectURL(file);
    const next = [...st.refs];
    while (next.length <= slot) next.push(null);
    // Revoke the old object URL if we're replacing an existing pick.
    if (next[slot] && next[slot].previewUrl) URL.revokeObjectURL(next[slot].previewUrl);
    next[slot] = { file, name: file.name, size: file.size, previewUrl: url };
    set({ refs: next });
  };
  const clearRef = (slot) => {
    const next = [...st.refs];
    if (next[slot] && next[slot].previewUrl) URL.revokeObjectURL(next[slot].previewUrl);
    next[slot] = null;
    set({ refs: next });
  };
  const fmtSize = (b) => b < 1024*1024 ? (b/1024).toFixed(0) + " KB" : (b/1024/1024).toFixed(1) + " MB";

  const [stageTab, setStageTab] = useState("mockup");
  const [copied, setCopied] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genElapsed, setGenElapsed] = useState(0);   // seconds, live while generating
  const [eta, setEta] = useState(() => localEta(null, null, "1K", 0));
  // When true, the next /api/generate call attaches the most recent gallery
  // image as scene_image — locking the backdrop pixel-perfectly across
  // re-renders. Same mechanism the Warianty tab uses for cross-variant
  // background consistency. Disabled until at least one render exists.
  const [lockBackground, setLockBackground] = useState(false);
  const [genError, setGenError] = useState("");
  // Each item: {url, generation_id, color(hex), material(id), tag, cost, ts}.
  // generation_id lets any render be reused as a Fotosesja anchor; the list is
  // persisted (durable fields only — all urls are stable /api/outputs paths).
  const [gallery, setGallery] = useState(() => {
    try { return JSON.parse(localStorage.getItem(GALLERY_STORAGE) || "[]"); } catch { return []; }
  });
  useEffect(() => {
    try {
      const slim = gallery.slice(0, 60).map(g => ({
        url: g.url, generation_id: g.generation_id || null,
        color: g.color || null, color_id: g.color_id || null, fabric_code: g.fabric_code || null,
        product_name: g.product_name || null,
        material: g.material || null, catalog_profile: g.catalog_profile || null,
        tag: g.tag || null, cost: g.cost ?? null, ts: g.ts || null,
      }));
      localStorage.setItem(GALLERY_STORAGE, JSON.stringify(slim));
    } catch {}
  }, [gallery]);
  const [activeGallery, setActiveGallery] = useState(-1);

  // Color-variant set state. variantColors is the user's multi-pick of color
  // ids (first = anchor). variantMaterials is paired positionally — empty
  // means every variant uses the shared section-04 material; otherwise each
  // entry overrides the material for the corresponding color index. If
  // shorter than variantColors, the last material extends to remaining slots
  // (matches the server's fill-with-last fallback). variantSet is the result
  // strip after the server returns { anchor, variants[] } from /api/generate-set.
  const [variantColors, setVariantColors]       = useState([]);   // English color ids
  const [variantMaterials, setVariantMaterials] = useState([]);   // English material ids, paired positionally
  const [variantSet, setVariantSet]             = useState(null); // { anchor, variants, total_cost }
  const [variantBusy, setVariantBusy]           = useState(false);
  const [variantError, setVariantError]         = useState("");

  // Fotosesja v2 = apply a shared set of colour+material PAIRS to MANY base
  // photos. Sources are uploaded photos and/or picks from this session's gallery
  // / server history. Each (source × pair) is an in-place recolor that keeps the
  // source photo's exact angle + background and changes only colour/material.
  const [shootSources, setShootSources] = useState([]);        // [{sid, kind:'upload'|'ref', file?, ref?, url, color?, material?}]
  const [shootSourceTab, setShootSourceTab] = useState("session"); // grid picker: "session" | "history"
  const [historyItems, setHistoryItems] = useState(null);      // null = not loaded yet, [] = loaded empty
  const [historyBusy, setHistoryBusy] = useState(false);
  const [shootPairs, setShootPairs] = useState([]);            // [{color, material}] shared across all sources
  const [shootPairDraft, setShootPairDraft] = useState({ color: null, material: null });
  const [shootGrid, setShootGrid] = useState(null);            // { sources:[{sid,...,variants}], total_cost }
  const [shootRegen, setShootRegen] = useState({});            // { "<sid>|<color>|<material>": true } in-flight tiles
  const [shootBusy, setShootBusy] = useState(false);
  const [shootError, setShootError] = useState("");
  const [shootProgress, setShootProgress] = useState(null);    // { done, total } while a grid run streams
  const [shootElapsed, setShootElapsed] = useState(0);         // seconds, live while the grid streams

  const colorObj = useMemo(() => COLORS.find(c => c.id === st.color), [st.color]);
  const matObj   = useMemo(() => MATERIALS.find(m => m.id === st.mat), [st.mat]);
  const sizes    = st.kind === "bed" ? SIZES_BED : SIZES_SOFA;
  const sizeObj  = useMemo(() => sizes.find(s => s.id === st.size) || sizes[0], [sizes, st.size]);
  // Beds skip legs unless the user opts in; sofas always send their leg choice.
  const bedLegsHidden = st.kind === "bed" && !st.bedLegs;
  const effectiveLegs = bedLegsHidden ? "keep" : st.legs;
  // "Keep base camera" only applies while a base photo is loaded. A preset saved
  // with it on (or a removed base) must not leave the camera grids locked
  // behind a checkbox that is itself disabled and shown unchecked.
  const baseCamLocked = st.uploaded && !!st.preserveBaseCamera;
  const camObj   = useMemo(() => CAMERAS.find(c => c.id === st.cam), [st.cam]);
  // The Szybki preset tile stays highlighted only while the seeded structured
  // fields still match — clicking "Detal makro" then changing the shot type
  // chip auto-deselects the preset, so the row never lies about current state.
  const matchedPreset = useMemo(() => {
    for (const [presetId, seed] of Object.entries(CAM_PRESET_DEFAULTS)) {
      if (seed.shot   !== st.shot)   continue;
      if (seed.yaw    !== st.yaw)    continue;
      if (seed.height !== st.height) continue;
      if (seed.lens   !== st.lens)   continue;
      if (seed.dof    !== st.dof)    continue;
      if (seed.detailRegion && seed.detailRegion !== st.detailRegion) continue;
      return presetId;
    }
    return null;
  }, [st.shot, st.yaw, st.height, st.lens, st.dof, st.detailRegion]);
  const bgObj = useMemo(() => BACKGROUNDS.find(b => b.id === st.bg) || BACKGROUNDS[0], [st.bg]);
  // A locked backdrop = the catalog treatment (lens / light locks, framing
  // contract, curated plate, normalization), decided by catalog.json.
  const bgLocked = !!bgObj?.locked;
  // Choosing a background. Moving onto a locked backdrop seeds its camera
  // defaults (85 mm, f/8, eye level); moving off one restores the lifestyle
  // defaults. Shot type and detail region are never touched — they are the
  // user's, under any background (phase 4).
  const pickBackground = (b) => {
    const patch = { bg: b.id };
    if (b.locked && !bgLocked) {
      const d = b.cameraDefaults || {};
      Object.assign(patch, { lens: d.lens || "85mm_product", dof: d.dof || "deep", height: d.height || "eye" });
    } else if (!b.locked && bgLocked) {
      Object.assign(patch, { lens: "50mm_natural", dof: "standard" });
    }
    set(patch);
  };
  const lensObj   = useMemo(() => LENSES.find(l => l.id === st.lens),         [st.lens]);
  const todObj    = useMemo(() => TIMES_OF_DAY.find(t => t.id === st.tod),    [st.tod]);
  const shadowObj = useMemo(() => SHADOWS.find(s => s.id === st.shadow),      [st.shadow]);

  // The `color_custom` string the server injects verbatim into the prompt when
  // color === "custom". Merges the free-text description with the optional HEX
  // pick so the model gets both the words and an exact shade anchor.
  const customColorText = useCallback(() => {
    const txt = (st.colorCustom || "").trim();
    const hex = (st.colorCustomHex || "").trim();
    if (!hex) return txt;
    const hexNote = `exact upholstery colour hex ${hex}`;
    return txt ? `${txt} (${hexNote})` : hexNote;
  }, [st.colorCustom, st.colorCustomHex]);

  const modelObj = useMemo(
    () => serverConfig.models.find(m => m.id === st.model) || serverConfig.models[0],
    [serverConfig, st.model],
  );
  // The key the active engine needs — Gemini in the studio; in the Lab the
  // selected model's provider: OpenAI direct or OpenRouter ("openai/…" slugs).
  const labViaOpenRouter = isLab && (modelObj?.provider === "openrouter" || st.model.includes("/"));
  const keyName = !isLab ? "Gemini" : labViaOpenRouter ? "OpenRouter" : "OpenAI";
  const activeKey = !isLab ? apiKey : labViaOpenRouter ? orKey : oaKey;
  const setActiveKey = !isLab ? setApiKey : labViaOpenRouter ? setOrKey : setOaKey;
  const keyHint = `Wklej klucz ${keyName}${isLab ? "" : " API"} u góry sceny.`;
  const keyCode = !isLab ? "MISSING_API_KEY" : labViaOpenRouter ? "MISSING_OPENROUTER_KEY" : "MISSING_OPENAI_KEY";
  // Display name for any model id (history rows, chips) — from the registry,
  // never derived from the id string.
  const modelShort = (id) => (serverConfig.models.find(m => m.id === id) || {}).short || id || "—";
  // Registry price for the current model at a resolution ("1K" when unknown).
  const modelPrice = (res) => {
    const table = modelObj?.pricing || {};
    const r = (res || "1K").split(" ")[0];
    return Number(table[r] ?? table["1K"] ?? 0);
  };

  // If the server's catalogue doesn't include the currently-selected model
  // (e.g. dev edited the schema), snap to the server default. Same for resolution
  // when the chosen one isn't in the active model's allow-list.
  useEffect(() => {
    if (!serverConfig.models.length) return;
    const knownIds = serverConfig.models.map(m => m.id);
    if (!knownIds.includes(st.model)) {
      set({ model: serverConfig.default_model });
      return;
    }
    const allowedRes = modelObj?.resolutions || ["1K"];
    const currentRes = (st.res || "").split(" ")[0];   // "1K — Flash limit" → "1K"
    if (!allowedRes.includes(currentRes)) {
      set({ res: allowedRes[0] });
    }
    const qualities = modelObj?.qualities || [];
    setQuality(q => qualities.includes(q) ? q : (modelObj?.default_quality || ""));
  }, [serverConfig, st.model]);

  const cost = useMemo(() => {
    const refMult = 1 + st.refs.filter(Boolean).length * 0.15;
    return (modelPrice(st.res) * refMult).toFixed(3);
  }, [modelObj, st.refs, st.res]);

  // Honest ETA: ask the server for a measured-or-estimated duration whenever the
  // model / resolution / reference-count changes. Debounced so dragging controls
  // doesn't spam the endpoint. Replaces the old hardcoded "~12 s".
  useEffect(() => {
    const refs = st.refs.filter(Boolean).length;
    const res = (st.res || "1K").split(" ")[0];
    // Instant, model-aware estimate so the overlay reflects the current pick
    // immediately (and survives /api/eta being unavailable).
    setEta(localEta(modelObj, serverConfig.eta_seed, res, refs));
    const t = setTimeout(() => {
      fetch(`/api/eta?model=${encodeURIComponent(st.model)}&resolution=${encodeURIComponent(res)}&refs=${refs}`)
        .then(r => (r.ok ? r.json() : null))
        .then(d => { if (d && d.p50_s) setEta(d); })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [st.model, st.res, st.refs]);

  // Live elapsed timer while a single render is in flight ("is it stuck?").
  useEffect(() => {
    if (!generating) { setGenElapsed(0); return; }
    const start = Date.now();
    setGenElapsed(0);
    const id = setInterval(() => setGenElapsed((Date.now() - start) / 1000), 250);
    return () => clearInterval(id);
  }, [generating]);

  // Live elapsed timer for the Fotosesja grid run (streamed, tiles fill in).
  useEffect(() => {
    if (!shootBusy) { setShootElapsed(0); return; }
    const start = Date.now();
    setShootElapsed(0);
    const id = setInterval(() => setShootElapsed((Date.now() - start) / 1000), 250);
    return () => clearInterval(id);
  }, [shootBusy]);

  // ONE request builder for Generuj / Warianty / Seria and for the JSON tab:
  // the preview is derived from the very entries that go on the wire.
  const requestCtx = {
    isLab, apiKey, oaKey, quality, effectiveLegs, customColorText: customColorText(),
    labKeyField: labViaOpenRouter ? "openrouter_key" : "openai_key", labKey: activeKey, baseCamLocked,
    bgObj, bgLocked, prevRender: (!bgLocked && lockBackground && gallery[0]?.url) ? "pending" : null,
    variantColors, variantMaterials, catalogRefs, colorObj, matObj, sizeObj, modelObj,
    matchedPreset, bedLegsHidden,
  };
  const built = useMemo(() => buildRequest(st, { ...requestCtx, mode: "generate" }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [st, isLab, apiKey, oaKey, orKey, quality, effectiveLegs, baseCamLocked, bgObj, bgLocked, lockBackground, gallery,
     variantColors, variantMaterials, catalogRefs, colorObj, matObj, sizeObj, modelObj, matchedPreset, bedLegsHidden]);
  const jsonPayload = built.preview;
  const budget = built.budget;

  // The previous render as the scene, fetched only when the toggle is on.
  const fetchPrevRender = async () => {
    if (bgLocked || !lockBackground || !gallery[0]?.url) return null;
    try {
      const prev = await fetch(gallery[0].url);
      const blob = await prev.blob();
      const ext = (gallery[0].url.split(".").pop() || "png").split("?")[0];
      return new File([blob], `prev-render.${ext}`, { type: blob.type || "image/png" });
    } catch (e) {
      console.warn("Background lock failed, continuing without it:", e);
      return null;
    }
  };

  const handleGenerate = async () => {
    setGenError("");
    if (!activeKey.trim()) { setGenError(mkErr(keyHint, keyCode)); setShowKeyEdit(true); return; }
    if (!st.baseFile) { setGenError(mkErr("Wgraj zdjęcie bazowe (sekcja 02).", "MISSING_BASE_IMAGE")); return; }

    const prevRender = await fetchPrevRender();
    const fd = toFormData(buildRequest(st, { ...requestCtx, mode: "generate", prevRender }).entries);

    setGenerating(true);
    try {
      const r = await fetch("/api/generate", { method: "POST", body: fd });
      let data = null;
      try { data = await r.json(); } catch { /* non-JSON body (proxy error page) */ }
      if (!r.ok || !data || data.error) {
        setGenError(errorFromResponse(r, data));
      } else {
        setGallery(g => [
          { url: data.image_url, generation_id: data.generation_id || null,
            color: st.color === "custom" ? (st.colorCustomHex || null) : (colorObj?.hex || null),
            color_id: st.color === "custom" ? "custom" : (colorObj?.id || null),
            fabric_code: colorObj?.fabricCode || null,
            product_name: st.product.trim() || null,
            material: matObj?.id || null,
            catalog_profile: data.catalog_profile || null,
            tag: "v" + (g.length + 1), cost: data.cost, ts: Date.now() },
          ...g,
        ]);
        setActiveGallery(0);
      }
    } catch (e) {
      setGenError(errorFromException(e));
    } finally {
      setGenerating(false);
    }
  };

  // When the user switches sofa↔bed, snap st.size onto the new list. Skip the
  // initial mount so the chosen default size (e.g. bed "160") is respected —
  // running it on mount was clobbering the default down to sizes[0] ("90").
  const kindSwitched = React.useRef(false);
  useEffect(() => {
    if (!kindSwitched.current) { kindSwitched.current = true; return; }
    if (!sizes.find(s => s.id === st.size)) set({ size: sizes[0].id });
    // eslint-disable-next-line
  }, [st.kind]);

  // Toggle a color in the variant pick list. First entry is the anchor.
  const toggleVariantColor = (cid) => {
    setVariantColors(prev =>
      prev.includes(cid) ? prev.filter(c => c !== cid) : [...prev, cid]
    );
  };
  // Toggle a material in the per-variant material list. Pick order is
  // paired positionally with the colors list — picking 3 materials in a
  // batch of 3 colors means color[i] uses material[i]. Picking fewer
  // materials than colors lets the server reuse the last material for
  // remaining slots, so a single-material pick stays the simplest path.
  const toggleVariantMaterial = (mid) => {
    setVariantMaterials(prev =>
      prev.includes(mid) ? prev.filter(m => m !== mid) : [...prev, mid]
    );
  };

  // Estimated cost for the whole set (anchor + N variants) using the same
  // per-render multipliers as the single-render cost calc above.
  const variantSetCost = useMemo(() => {
    const base = modelPrice(st.res);
    // Each non-anchor variant has 1 extra reference (the anchor png), so apply 1.15× ref multiplier.
    const anchorCost = base;
    const variantCost = base * 1.15;
    return (anchorCost + variantCost * Math.max(0, variantColors.length - 1)).toFixed(3);
  }, [modelObj, st.res, variantColors.length]);

  // -------- Fotosesja v2 (variant grid from many base photos) handlers ------
  const SID = () => "s" + Math.random().toString(36).slice(2, 10);

  // Add uploaded base photos (capped at 8 sources total).
  const addUploadSources = (files) => {
    const arr = Array.from(files || []);
    if (!arr.length) return;
    setShootSources(prev => {
      const next = [...prev];
      for (const f of arr) {
        if (next.length >= 8) break;
        next.push({ sid: SID(), kind: "upload", file: f, url: URL.createObjectURL(f), name: f.name });
      }
      return next;
    });
  };
  // Add an existing render (from session gallery or server history) as a source.
  const addRefSource = (it) => {
    const ref = it.generation_id || (it.image_url || "").split("/").pop();
    if (!ref) return;
    setShootSources(prev => {
      if (prev.some(s => s.kind === "ref" && s.ref === ref)) return prev;   // dedupe
      if (prev.length >= 8) return prev;
      return [...prev, { sid: "r_" + ref, kind: "ref", ref, url: it.image_url,
                         color: it.color || null, material: it.material || null }];
    });
  };
  const removeSource = (sid) => {
    setShootSources(prev => {
      const s = prev.find(x => x.sid === sid);
      if (s?.kind === "upload" && s.url) { try { URL.revokeObjectURL(s.url); } catch {} }
      return prev.filter(x => x.sid !== sid);
    });
  };

  // Lazy-load the server-side history of all past renders (across sessions).
  const loadHistory = async () => {
    setHistoryBusy(true);
    try {
      const r = await fetch("/api/history?limit=60");
      const data = await r.json();
      setHistoryItems(Array.isArray(data?.items) ? data.items : []);
    } catch {
      setHistoryItems([]);
    } finally {
      setHistoryBusy(false);
    }
  };
  useEffect(() => {
    if (shootSourceTab === "history" && historyItems === null && !historyBusy) loadHistory();
    // eslint-disable-next-line
  }, [shootSourceTab]);

  // Colour+material PAIR builder. The draft is one colour + one material;
  // "Dodaj parę" appends it to the shared list applied to every source.
  const addPair = () => {
    const { color, material } = shootPairDraft;
    if (!color || !material) return;
    setShootPairs(prev => {
      if (prev.some(p => p.color === color && p.material === material)) return prev;
      if (prev.length >= 8) return prev;
      return [...prev, { color, material }];
    });
  };
  const removePair = (idx) => setShootPairs(prev => prev.filter((_, i) => i !== idx));

  // Total renders = sources × pairs; each carries the source as a reference (1.15×).
  const shootGridCost = useMemo(() => {
    return (modelPrice(st.res) * 1.15 * shootSources.length * shootPairs.length).toFixed(3);
  }, [modelObj, st.res, shootSources.length, shootPairs.length]);

  // Shared scene/model/output config sent with both grid + per-tile regen.
  // Note: no `mat`/colour here — those come from the pairs (grid) or the tile (regen).
  const appendShootConfig = (fd) => {
    for (const [k, v] of buildRequest(st, { ...requestCtx, mode: "shoot" }).entries) fd.append(k, v);
  };

  const handleGenerateGrid = async () => {
    setShootError("");
    setShootGrid(null);
    if (!activeKey.trim()) { setShootError(mkErr(keyHint, keyCode)); setShowKeyEdit(true); return; }
    if (!shootSources.length) { setShootError(mkErr("Dodaj co najmniej 1 zdjęcie bazowe (wgraj lub wybierz z sesji/historii).", "MISSING_SOURCES")); return; }
    if (!shootPairs.length) { setShootError(mkErr("Dodaj co najmniej 1 parę kolor + materiał.", "TOO_FEW_PAIRS")); return; }
    if (shootSources.length * shootPairs.length > 48) { setShootError(mkErr("Za dużo renderów (limit 48). Zmniejsz liczbę zdjęć lub par.", "TOO_MANY_RENDERS")); return; }

    // Snapshot the run so later edits to sources/pairs don't disturb it.
    const runSources = shootSources.map(s => ({ sid: s.sid, source_kind: s.kind, source_ref: s.ref || null, source_url: s.url || null }));
    const runPairs = shootPairs.map(p => ({ ...p }));

    // Show the full grid skeleton immediately — every cell starts "pending" and
    // fills in as its tile streams back.
    setShootGrid({
      total_cost: 0,
      sources: runSources.map(s => ({ ...s, error: null,
        variants: runPairs.map(p => ({ color: p.color, material: p.material, pending: true })) })),
    });
    setShootProgress({ done: 0, total: runSources.length * runPairs.length });

    const fd = new FormData();
    appendShootConfig(fd);
    fd.append("pairs_json", JSON.stringify(runPairs));
    const uploadSids = [], refList = [], refSids = [];
    for (const s of shootSources) {
      if (s.kind === "upload" && s.file) { fd.append("sources", s.file); uploadSids.push(s.sid); }
      else if (s.kind === "ref" && s.ref) { refList.push(s.ref); refSids.push(s.sid); }
    }
    fd.append("upload_sids_csv", uploadSids.join(","));
    fd.append("source_refs_csv", refList.join(","));
    fd.append("ref_sids_csv", refSids.join(","));

    // --- stream message handlers (NDJSON: meta → tile* → done) ---
    const onMeta = (msg) => {
      const errBySid = {};
      (msg.sources || []).forEach(ms => { if (ms.error) errBySid[ms.sid] = ms.error; });
      if (Object.keys(errBySid).length) {
        setShootGrid(prev => prev ? ({ ...prev, sources: prev.sources.map(sg =>
          errBySid[sg.sid] ? ({ ...sg, error: errBySid[sg.sid], variants: [] }) : sg) }) : prev);
      }
      if (typeof msg.total === "number") setShootProgress(p => p ? ({ ...p, total: msg.total }) : { done: 0, total: msg.total });
    };
    const onTile = (msg) => {
      setShootGrid(prev => {
        if (!prev) return prev;
        const sources = prev.sources.map(sg => {
          if (sg.sid !== msg.sid) return sg;
          const variants = sg.variants.map(v =>
            (v.color === msg.color && (v.material || "") === (msg.material || ""))
              ? (msg.error
                  ? { color: msg.color, material: msg.material, error: msg.error }
                  : { color: msg.color, material: msg.material, image_url: msg.image_url, generation_id: msg.generation_id, cost: msg.cost })
              : v);
          return { ...sg, variants };
        });
        return { ...prev, sources, total_cost: (prev.total_cost || 0) + (msg.cost || 0) };
      });
      setShootProgress(p => p ? ({ ...p, done: p.done + 1 }) : p);
      if (msg.image_url && msg.generation_id) {
        setGallery(g => [{ url: msg.image_url, generation_id: msg.generation_id,
          color: COLORS.find(c => c.id === msg.color)?.hex || null, material: msg.material || null,
          tag: "fs", cost: msg.cost, ts: Date.now() }, ...g]);
      }
    };
    const onDone = (msg) => {
      if (typeof msg.total_cost === "number") setShootGrid(prev => prev ? ({ ...prev, total_cost: msg.total_cost }) : prev);
    };

    setShootBusy(true);
    try {
      const resp = await fetch("/api/generate-variants", { method: "POST", body: fd });
      if (!resp.ok || !resp.body) {
        // Pre-flight validation error arrives as normal JSON before the stream.
        let data = null; try { data = await resp.json(); } catch { /* non-JSON */ }
        setShootError(errorFromResponse(resp, data));
        setShootGrid(null);
        return;
      }
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          let msg; try { msg = JSON.parse(line); } catch { continue; }
          if (msg.type === "meta") onMeta(msg);
          else if (msg.type === "tile") onTile(msg);
          else if (msg.type === "done") onDone(msg);
        }
      }
    } catch (e) {
      setShootError(errorFromException(e));
    } finally {
      setShootBusy(false);
      setShootProgress(null);
    }
  };

  // Re-render ONE tile (source × colour+material) — fixes a single bad render.
  const regenerateTile = async (source, color, material) => {
    if (!activeKey.trim()) { setShootError(mkErr(keyHint, keyCode)); setShowKeyEdit(true); return; }
    const key = source.sid + "|" + color + "|" + (material || "");
    setShootRegen(prev => ({ ...prev, [key]: true }));
    try {
      const fd = new FormData();
      appendShootConfig(fd);
      fd.append("color", color);
      fd.append("material", material || "boucle");
      fd.append("mat", material || "boucle");
      if (source.kind === "ref" && source.ref) fd.append("source_ref", source.ref);
      else if (source.kind === "upload" && source.file) fd.append("source_image", source.file);
      const resp = await fetch("/api/regenerate-variant", { method: "POST", body: fd });
      let data = null;
      try { data = await resp.json(); } catch { /* non-JSON */ }
      if (resp.ok && data && !data.error && data.image_url) {
        setShootGrid(prev => {
          if (!prev) return prev;
          const sources = prev.sources.map(sg => {
            if (sg.sid !== source.sid) return sg;
            const variants = sg.variants.map(v =>
              (v.color === color && (v.material || "") === (material || ""))
                ? { color, material, image_url: data.image_url, generation_id: data.generation_id, cost: data.cost }
                : v);
            return { ...sg, variants };
          });
          return { ...prev, sources };
        });
        if (data.generation_id) setGallery(g => [{ url: data.image_url, generation_id: data.generation_id,
          color: COLORS.find(c => c.id === color)?.hex || null, material: material || null, tag: "fs", cost: data.cost, ts: Date.now() }, ...g]);
      } else {
        setShootError(errorFromResponse(resp, data));
      }
    } catch (e) {
      setShootError(errorFromException(e));
    } finally {
      setShootRegen(prev => { const n = { ...prev }; delete n[key]; return n; });
    }
  };

  const handleGenerateSet = async () => {
    setVariantError("");
    setVariantSet(null);
    if (!activeKey.trim()) { setVariantError(mkErr(keyHint, keyCode)); setShowKeyEdit(true); return; }
    if (!st.baseFile)   { setVariantError(mkErr("Wgraj zdjęcie bazowe (sekcja 02).", "MISSING_BASE_IMAGE")); return; }
    if (variantColors.length < 2) { setVariantError(mkErr("Wybierz co najmniej 2 kolory.", "TOO_FEW_COLORS")); return; }

    const prevRender = await fetchPrevRender();
    const fd = toFormData(buildRequest(st, { ...requestCtx, mode: "set", prevRender }).entries);

    setVariantBusy(true);
    try {
      const r = await fetch("/api/generate-set", { method: "POST", body: fd });
      let data = null;
      try { data = await r.json(); } catch { /* non-JSON body */ }
      if (!r.ok || !data || data.error) {
        setVariantError(errorFromResponse(r, data));
      } else {
        setVariantSet(data);
        // Surface the whole set in the cross-tab gallery so any of these
        // renders can later be picked as a Fotosesja anchor.
        const fresh = [data.anchor, ...(data.variants || [])]
          .filter(v => v && v.image_url && v.generation_id)
          .map(v => ({ url: v.image_url, generation_id: v.generation_id,
                       color: COLORS.find(c => c.id === v.color)?.hex || null,
                       material: v.material || null,
                       product_name: st.product.trim() || null,
                       catalog_profile: data.catalog_profile || null,
                       tag: "set", cost: v.cost, ts: Date.now() }));
        if (fresh.length) setGallery(g => [...fresh, ...g]);
      }
    } catch (e) {
      setVariantError(errorFromException(e));
    } finally {
      setVariantBusy(false);
    }
  };

  return (
    <div className="app-frame">
      <NanoTopbar active={isLab ? "lab" : "photos"} apiKey={activeKey} setApiKey={setActiveKey} showKeyEdit={showKeyEdit} setShowKeyEdit={setShowKeyEdit}
        keyName={keyName} keyPlaceholder={!isLab ? "AIza… wklej klucz Gemini" : labViaOpenRouter ? "sk-or-… wklej klucz OpenRouter" : "sk-… wklej klucz OpenAI"} />

      {catalogStale && (
        <div role="status" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 14, padding: "8px 16px",
          background: "var(--ink)", color: "var(--paper)", fontSize: 12.5 }}>
          <span>Katalog tkanin został zaktualizowany. Odśwież stronę, żeby zobaczyć nowe kolory i materiały.</span>
          <button type="button" onClick={() => window.location.reload()}
            style={{ border: "1px solid rgba(255,255,255,.5)", background: "transparent", color: "inherit", borderRadius: 999, padding: "3px 12px", fontSize: 12, cursor: "pointer" }}>
            Odśwież
          </button>
          <button type="button" onClick={() => setCatalogStale(false)} title="ukryj"
            style={{ border: 0, background: "transparent", color: "inherit", opacity: .7, cursor: "pointer", fontSize: 14 }}>×</button>
        </div>
      )}
      <div className="shell">
      {/* ============= LEFT — sticky stage ============= */}
      <section className="stage-pane">
        <div className="stage-tabs">
          <button className={stageTab === "mockup" ? "on" : ""} onClick={() => setStageTab("mockup")}>Podgląd</button>
          <button className={stageTab === "variants" ? "on" : ""} onClick={() => setStageTab("variants")}>Warianty</button>
          <button className={stageTab === "photoshoot" ? "on" : ""} onClick={() => setStageTab("photoshoot")}>Seria</button>
          <button className={"stage-tech-tab " + (stageTab === "json" ? "on" : "")} title="Dane techniczne" onClick={() => setStageTab("json")}>•••</button>
        </div>

        <div className="stage-canvas" style={{
          background: bgObj?.preview,
          "--stage-zoom": (t.stageZoom / 100),
          "--vignette-opacity": t.stageVignette ? 0.18 : 0,
        }}>
          {stageTab === "mockup" && (() => {
            const showGen = activeGallery >= 0 && gallery[activeGallery] && gallery[activeGallery].url;
            if (showGen) {
              return <img src={gallery[activeGallery].url} alt="rendering"
                          style={{position:"absolute", inset:"6% 6% 14% 6%", width:"88%", height:"80%", objectFit:"contain"}} />;
            }
            const tex = matObj?.tex || "linen";
            return (
              <>
                {st.kind === "bed" ? (
                  <div className={"bed mat-" + tex} style={{
                    "--mat-color": colorObj?.hex || "#6F8C68",
                    width: Math.min(t.sofaWidth + 10, 90) + "%",
                    bottom: t.sofaBottom + "%",
                    "--shadow-strength": t.shadowStrength / 100,
                  }}>
                    <div className="bed-headboard">
                      <div className={"fabric-overlay " + tex}></div>
                      <div className="fabric-sheen"></div>
                    </div>
                    <div className="bed-base">
                      <div className={"fabric-overlay " + tex}></div>
                      <div className="fabric-sheen"></div>
                    </div>
                    <div className="bed-mattress"></div>
                    <div className="bed-pillow p1"></div>
                    <div className="bed-pillow p2"></div>
                    {st.bedLegs && (
                      <div className="bed-legs">
                        {Array.from({ length: 4 }).map((_, i) => <span key={i} />)}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className={"sofa mat-" + tex} style={{
                    "--mat-color": colorObj?.hex || "#6F8C68",
                    width: t.sofaWidth + "%",
                    bottom: t.sofaBottom + "%",
                    aspectRatio: `${t.sofaAspect} / 1`,
                    borderRadius: `${t.sofaRadius}px ${t.sofaRadius}px 8px 8px`,
                    boxShadow: `0 28px 50px -22px rgba(0,0,0,${t.shadowStrength/100}), inset 0 -8px 0 -3px rgba(0,0,0,.10)`,
                  }}>
                    <div className={"fabric-overlay " + tex}></div>
                    <div className="fabric-sheen"></div>
                    <div className="sofa-legs">
                      {Array.from({ length: 4 }).map((_, i) => <span key={i} />)}
                    </div>
                  </div>
                )}
                {matObj && (
                  <div className="fabric-caption">
                    <span className="fc-mat">{matObj.name}</span>
                    <span className="fc-dot">·</span>
                    <span className="fc-finish">{matObj.finish}</span>
                    <span className="fc-sep"></span>
                    <span className="fc-chip" style={{ background: st.color === "custom" ? (st.colorCustomHex || "conic-gradient(#d8d3c8,#f2eee4,#d8d3c8)") : (colorObj?.hex || "#ccc") }}></span>
                    <span>{st.color === "custom" ? "własny odcień" : (colorObj?.name || "—")}</span>
                    {st.color === "custom" && st.colorCustomHex && <span className="fc-hex">{st.colorCustomHex}</span>}
                    {st.color !== "custom" && colorObj && <span className="fc-hex">{colorObj.hex}</span>}
                  </div>
                )}
              </>
            );
          })()}

          {stageTab === "mockup" && t.showFloorTag && <div className="stage-summary-top">
            <div className="line"><span className="k">kolor</span><span className="v serif">{colorObj?.name || "—"}</span></div>
            <div className="line"><span className="k">tkanina</span><span className="v serif">{matObj?.name || "—"}</span></div>
            <div className="line"><span className="k">format</span><span className="v serif">{sizeObj?.name} · {sizeObj?.dim}</span></div>
            <div className="line"><span className="k">scena</span><span className="v serif">
              {bgObj?.name}
            </span></div>
          </div>}

          {/* variant rail — vertical, right edge */}
          {stageTab === "mockup" && t.showVariantRail && gallery.length > 0 && <div className="variant-rail">
            {gallery.map((g, i) => (
              <div key={i}
                className={"v-thumb " + (i === activeGallery ? "active" : "")}
                style={{ "--vc": g.color }}
                onClick={() => setActiveGallery(i)}>
                {g.url
                  ? <img src={g.url} alt={g.tag} style={{position:"absolute", inset:0, width:"100%", height:"100%", objectFit:"cover"}} />
                  : <div className="vt-render"></div>}
                <div className="tag">{g.tag}</div>
              </div>
            ))}
          </div>}

          {stageTab === "mockup" && (() => {
            const activeImg = activeGallery >= 0 && gallery[activeGallery] && gallery[activeGallery].url ? gallery[activeGallery] : null;
            let downloadName = "";
            let ext = "jpg";
            if (activeImg) {
              const tag = activeImg.tag || ("v" + (activeGallery + 1));
              const sceneId = activeImg.background || activeImg.catalog_profile || bgObj?.id;
              const slug = fileSlug(activeImg.product_name, activeImg.fabric_code || activeImg.color_id || colorObj?.id,
                activeImg.material || matObj?.id, sceneId);
              ext = (activeImg.url.split(".").pop() || "jpg").split("?")[0];
              downloadName = `nano-sofa-${tag}-${slug || "render"}.${ext}`;
            }
            return (
              <div className="stage-actions" style={{
                position: "absolute", bottom: 24, zIndex: 4,
                display: "flex", alignItems: "center", gap: 10,
                left:      t.fabAlign === "left"   ? 24    : t.fabAlign === "right" ? "auto" : "50%",
                right:     t.fabAlign === "right"  ? 24    : "auto",
                transform: t.fabAlign === "center" ? "translateX(-50%)" : "none",
              }}>
                {activeImg && (
                  <a className="stage-download"
                     href={activeImg.url}
                     download={downloadName}
                     title={"Pobierz " + ext.toUpperCase()}
                     style={{
                       display: "flex", alignItems: "center", gap: 8,
                       padding: "11px 16px", fontSize: 13, fontFamily: "Geist",
                       background: "rgba(255,255,255,.92)", color: "var(--ink)",
                       borderRadius: 999, textDecoration: "none",
                       border: "0.5px solid rgba(0,0,0,.12)",
                       boxShadow: "var(--shadow-pop)",
                       cursor: "pointer",
                       letterSpacing: "-0.005em",
                     }}>
                    <span style={{display:"inline-flex", transform:"rotate(180deg)"}}>{Ic.upload}</span>
                    <span>Pobierz {ext.toUpperCase()}</span>
                  </a>
                )}
                <button className="gen-fab" onClick={handleGenerate} style={{
                  position: "static", transform: "none", left: "auto", right: "auto",
                }}>
                  <span className="ico">{Ic.sparkle}</span>
                  <span>Generuj wariant</span>
                  <span className="cost">${cost}</span>
                  <span className="kbd">⌘ ↵</span>
                </button>
              </div>
            );
          })()}

          {stageTab === "json" && (
            <div className="stage-json">
              <div className="stage-json-head">
                <button className={"stage-json-copy " + (copied ? "ok" : "")} onClick={() => {
                  navigator.clipboard?.writeText(JSON.stringify(jsonPayload, null, 2));
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1400);
                }}>
                  {copied ? <><span>{Ic.check}</span> Skopiowano</> : <><span>{Ic.copy}</span> Kopiuj</>}
                </button>
              </div>
              <pre><code dangerouslySetInnerHTML={{__html: highlightJson(JSON.stringify(jsonPayload, null, 2))}}/></pre>
            </div>
          )}

          {stageTab === "variants" && (
            <div className="stage-variants" style={{
              // Clear the stage-tabs (y≈18-48) which sit on top of the canvas.
              // Start below them (the wordmark now lives in the top bar).
              position:"absolute", top: 60, left: 0, right: 0, bottom: 0,
              display:"flex", flexDirection:"column", gap: 14,
              background:"var(--paper, #f4f0e5)",
              padding: "8px 24px 24px",
              overflow:"auto",
              zIndex: 2,
            }}>
              {/* Locked-setup summary — keep on one line; no wrap into tabs row.
                  Reflects the new section-08 structured fields (shot type +
                  region) and, for beds, the textile arrangement from section 10. */}
              {(() => {
                const shotObj = SHOT_TYPES.find(s => s.id === st.shot);
                let regionTable = null;
                if (st.shot === "detail_fabric") regionTable = DETAIL_REGIONS_FABRIC;
                else if (st.shot === "detail_corner") regionTable = DETAIL_REGIONS_CORNER;
                else if (st.shot === "close_up") regionTable = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
                const regionObj = regionTable ? regionTable.find(r => r.id === st.detailRegion) : null;
                const beddingObj = st.kind === "bed" ? BEDDING_PRESETS.find(b => b.id === st.bedding) : null;
                const sharedMat = variantMaterials.length === 0;
                return (
                  <div style={{
                    display:"flex", flexWrap:"wrap", alignItems:"baseline",
                    gap: "4px 10px", fontSize: 11,
                    color:"var(--ink-3)", fontFamily:"Geist Mono",
                    lineHeight: 1.5,
                  }}>
                    <span style={{color:"var(--ink-4, #888)"}}>Zablokowane:</span>
                    {sharedMat && <span><b style={{color:"var(--ink)"}}>{matObj?.name}</b></span>}
                    {!sharedMat && <span style={{color:"var(--ink)"}}>{variantMaterials.length}×material</span>}
                    <span>· {sizeObj?.name} ({sizeObj?.dim})</span>
                    <span>· {bgObj?.name}</span>
                    <span>· {shotObj?.name || camObj?.name}</span>
                    {regionObj && <span style={{color:"var(--ink)"}}>· {regionObj.name}</span>}
                    <span>· {lensObj?.name?.split(" — ")[0]}</span>
                    <span>· {todObj?.name?.split(" — ")[0]}</span>
                    {beddingObj && <span>· {beddingObj.name}</span>}
                    <span>· {modelShort(st.model)}</span>
                  </div>
                );
              })()}

              <div>
                <div style={{fontSize: 13, marginBottom: 6}}>Wybierz kolory (pierwszy = anchor, reszta dziedziczy scenę)</div>
                <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(72px, 1fr))", gap: 8}}>
                  {COLOR_GRID_ITEMS.map((item) => {
                    if (item.type === "label") return <div key={item.key} style={GRID_LABEL_STYLE}>{item.text}</div>;
                    const c = item.c;
                    const picked = variantColors.includes(c.id);
                    const idx = variantColors.indexOf(c.id);
                    return (
                      <button key={c.id}
                              onClick={() => toggleVariantColor(c.id)}
                              disabled={variantBusy}
                              style={{
                                position:"relative",
                                padding: 0, border: 0, cursor: "pointer",
                                borderRadius: 10, overflow:"hidden",
                                aspectRatio: "1 / 1",
                                background: c.hex,
                                outline: picked ? "2.5px solid var(--ink)" : "0.5px solid rgba(0,0,0,.15)",
                                outlineOffset: picked ? 1 : 0,
                                opacity: variantBusy ? 0.5 : 1,
                              }}
                              title={c.name}>
                        {picked && (
                          <span style={{
                            position:"absolute", top: 4, left: 4,
                            background: "var(--ink)", color: "var(--paper)",
                            fontSize: 10, padding: "1px 5px", borderRadius: 999,
                            fontFamily: "Geist Mono",
                          }}>{idx === 0 ? "anchor" : idx + 1}</span>
                        )}
                        <span style={{
                          position:"absolute", bottom: 4, left: 4, right: 4,
                          fontSize: 9, color: "rgba(255,255,255,.95)",
                          textShadow: "0 1px 1px rgba(0,0,0,.4)",
                          fontFamily: "Geist Mono", textAlign:"left",
                        }}>{c.name}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Materials row — optional. Picking nothing reuses the shared
                  section-04 material for every variant. Picking one or more
                  pairs them positionally with colors; if fewer than colors,
                  the last material extends to the remaining slots. */}
              <div>
                <div style={{fontSize: 13, marginBottom: 6, display:"flex", alignItems:"baseline", gap:8}}>
                  <span>Materiały (opcjonalne — paruj pozycyjnie z kolorami)</span>
                  {variantMaterials.length === 0 && (
                    <span style={{fontSize:11, color:"var(--ink-3)", fontFamily:"Geist Mono"}}>
                      → wszystkie warianty: <b>{matObj?.name}</b>
                    </span>
                  )}
                </div>
                <div style={{display:"flex", flexWrap:"wrap", gap: 8}}>
                  {MATERIALS.map(m => {
                    const picked = variantMaterials.includes(m.id);
                    const idx = variantMaterials.indexOf(m.id);
                    return (
                      <button key={m.id} type="button"
                        onClick={() => toggleVariantMaterial(m.id)}
                        disabled={variantBusy}
                        style={{
                          position:"relative",
                          padding:"7px 14px 7px 14px",
                          borderRadius: 999,
                          fontSize: 12.5, lineHeight: 1.2,
                          border: picked ? "1.5px solid var(--ink)" : "1px solid var(--line-2)",
                          background: picked ? "var(--bg-1)" : "transparent",
                          cursor: variantBusy ? "wait" : "pointer",
                          opacity: variantBusy ? 0.5 : 1,
                          fontWeight: picked ? 600 : 400,
                        }}>
                        {picked && (
                          <span style={{
                            background: "var(--ink)", color: "var(--paper)",
                            fontSize: 10, padding: "1px 6px", borderRadius: 999,
                            fontFamily: "Geist Mono", marginRight: 6,
                          }}>{idx === 0 ? "anchor" : idx + 1}</span>
                        )}
                        {m.name}
                      </button>
                    );
                  })}
                </div>
                {variantMaterials.length > 0 && variantColors.length > 0 && variantMaterials.length < variantColors.length && (
                  <div style={{
                    fontSize: 11, color: "var(--ink-3)", fontFamily: "Geist Mono",
                    marginTop: 6,
                  }}>
                    {variantColors.length - variantMaterials.length} warianty bez własnego materiału użyją: <b style={{color:"var(--ink)"}}>{MATERIALS.find(m => m.id === variantMaterials[variantMaterials.length - 1])?.name}</b>
                  </div>
                )}
              </div>

              <div style={{display:"flex", alignItems:"center", gap: 12, paddingTop: 4}}>
                <button onClick={handleGenerateSet}
                        disabled={variantBusy || variantColors.length < 2}
                        style={{
                          display:"flex", alignItems:"center", gap: 10,
                          padding: "11px 18px", borderRadius: 999,
                          background: "var(--ink)", color: "var(--paper)",
                          border: 0, cursor: variantBusy ? "wait" : "pointer",
                          fontSize: 13, letterSpacing: "-0.005em",
                          opacity: (variantColors.length < 2 || variantBusy) ? 0.5 : 1,
                        }}>
                  <span style={{display:"inline-flex"}}>{Ic.sparkle}</span>
                  <span>{variantBusy ? "Generuję zestaw…" : "Generuj zestaw"}</span>
                  <span style={{
                    fontFamily:"Geist Mono", fontSize: 11,
                    background:"rgba(255,255,255,.10)", padding:"3px 8px",
                    borderRadius: 999, color:"rgba(255,255,255,.75)",
                  }}>{variantColors.length} kol · ${variantSetCost}</span>
                </button>
                {variantColors.length > 0 && !variantBusy && (
                  <button onClick={() => setVariantColors([])}
                          style={{background:"transparent", border:0, fontSize: 11,
                                  color:"var(--ink-3)", cursor:"pointer"}}>
                    wyczyść
                  </button>
                )}
                {variantError && (
                  <ErrorCard info={variantError} onRetry={handleGenerateSet} onFixKey={() => setShowKeyEdit(true)} compact />
                )}
              </div>

              {variantBusy && (
                <div style={{display:"flex", alignItems:"center", gap: 10, padding: 10,
                              background:"rgba(0,0,0,.04)", borderRadius: 10, fontSize: 12}}>
                  <span className="ico">{Ic.sparkle}</span>
                  <span>Renderuję anchor (pierwszy kolor), potem warianty równolegle z dziedziczoną sceną…</span>
                </div>
              )}

              {variantSet && (
                <div style={{display:"flex", flexDirection:"column", gap: 10}}>
                  <div style={{fontSize: 12, color:"var(--ink-3)"}}>
                    Zestaw gotowy · ${variantSet.total_cost?.toFixed(3)} łącznie
                  </div>
                  <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(180px, 1fr))", gap: 10}}>
                    {[variantSet.anchor, ...variantSet.variants].map((v, i) => {
                      const cObj = COLORS.find(c => c.id === v.color);
                      // v.material is set when the server received a per-variant
                      // material (positional pairing). Falls back to the shared
                      // section-04 material when materials_csv was empty.
                      const vMatId = v.material || matObj?.id;
                      const vMatObj = MATERIALS.find(m => m.id === vMatId);
                      if (v.error) {
                        return (
                          <div key={i} style={{
                            padding: 12, borderRadius: 10, fontSize: 11,
                            background: "rgba(192, 57, 43, 0.08)", color: "#c0392b",
                          }}>
                            <div style={{fontWeight: 600}}>{cObj?.name || v.color} · {vMatObj?.name}</div>
                            <div style={{marginTop: 4}}>{v.error}</div>
                          </div>
                        );
                      }
                      const slug = fileSlug(st.product, cObj?.fabricCode || v.color, vMatId, bgObj?.id);
                      const ext = (v.image_url.split(".").pop() || "png").split("?")[0];
                      const dlName = `nano-sofa-${i === 0 ? "anchor" : "v" + (i + 1)}-${slug}.${ext}`;
                      return (
                        <div key={i} style={{
                          display:"flex", flexDirection:"column", gap: 6,
                          background:"#fff", borderRadius: 10, overflow:"hidden",
                          border: "0.5px solid rgba(0,0,0,.08)",
                        }}>
                          <div style={{aspectRatio:"4/3", background:"#f2f0e9", position:"relative"}}>
                            <img src={v.image_url} alt={v.color}
                                 style={{position:"absolute", inset: 0, width:"100%", height:"100%", objectFit:"cover"}} />
                            {i === 0 && (
                              <span style={{position:"absolute", top: 6, left: 6,
                                            background:"var(--ink)", color:"var(--paper)",
                                            fontSize: 9, padding: "2px 6px", borderRadius: 999,
                                            fontFamily:"Geist Mono"}}>anchor</span>
                            )}
                          </div>
                          <div style={{padding:"6px 10px", display:"flex", alignItems:"center", justifyContent:"space-between", gap: 6}}>
                            <div style={{display:"flex", alignItems:"center", gap: 6, minWidth:0, flex:1}}>
                              <span style={{width: 12, height: 12, borderRadius: 999, flexShrink:0,
                                            background: cObj?.hex || "#888",
                                            border:"0.5px solid rgba(0,0,0,.18)"}}></span>
                              <span style={{fontSize: 11, fontFamily:"Geist", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>
                                {cObj?.name || v.color}
                                <span style={{color:"var(--ink-3)", marginLeft: 4}}>· {vMatObj?.name}</span>
                              </span>
                            </div>
                            <a href={v.image_url} download={dlName} title={"Pobierz " + ext.toUpperCase()}
                               style={{
                                 display:"inline-flex", alignItems:"center", gap: 4,
                                 fontSize: 10, fontFamily: "Geist Mono",
                                 color:"var(--ink)", textDecoration:"none",
                                 padding:"3px 7px", borderRadius: 999,
                                 background:"rgba(0,0,0,.04)",
                               }}>
                              <span style={{display:"inline-flex", transform:"rotate(180deg)"}}>{Ic.upload}</span>
                              PNG
                            </a>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {stageTab === "photoshoot" && (
            <div className="stage-photoshoot" style={{
              position:"absolute", top: 100, left: 0, right: 0, bottom: 0,
              display:"flex", flexDirection:"column", gap: 16,
              background:"var(--paper, #f4f0e5)",
              padding: "8px 24px 24px",
              overflow:"auto",
              zIndex: 2,
            }}>
              {/* Purpose sub-header */}
              <div style={{
                display:"flex", flexWrap:"wrap", alignItems:"baseline",
                gap: "4px 10px", fontSize: 11,
                color:"var(--ink-3)", fontFamily:"Geist Mono", lineHeight: 1.5,
              }}>
                <span style={{color:"var(--ink-4, #888)"}}>Warianty dla wielu zdjęć:</span>
                <span>wgraj / wybierz zdjęcia → dodaj pary kolor+materiał → ten sam kąt i tło każdego zdjęcia</span>
              </div>

              {/* ============ 1 — Zdjęcia bazowe (wiele) ============ */}
              <div>
                <div style={{fontSize: 13, marginBottom: 6, display:"flex", alignItems:"center", gap: 10, flexWrap:"wrap"}}>
                  <span>1 · Zdjęcia bazowe <span style={{color:"var(--ink-3)", fontFamily:"Geist Mono", fontSize: 11}}>({shootSources.length}/8)</span></span>
                  <label style={{
                    display:"inline-flex", alignItems:"center", gap: 6, cursor: shootBusy ? "not-allowed" : "pointer",
                    fontSize: 11, fontFamily:"Geist Mono", padding:"4px 10px", borderRadius: 999,
                    background:"var(--ink)", color:"var(--paper)", opacity: shootBusy || shootSources.length >= 8 ? 0.5 : 1,
                  }}>
                    <input type="file" accept="image/*" multiple style={{display:"none"}}
                           disabled={shootBusy || shootSources.length >= 8}
                           onChange={e => { addUploadSources(e.target.files); e.target.value = ""; }} />
                    <span style={{display:"inline-flex"}}>{Ic.upload}</span> Wgraj
                  </label>
                </div>

                {/* selected sources */}
                {shootSources.length > 0 && (
                  <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(100px, 1fr))", gap: 8, marginBottom: 10}}>
                    {shootSources.map(s => (
                      <div key={s.sid} style={{position:"relative", background:"#fff", borderRadius: 10, overflow:"hidden", border:"1px solid var(--ink)"}}>
                        <div style={{aspectRatio:"1/1", background:"#f2f0e9"}}>
                          <img src={s.url} alt="" style={{width:"100%", height:"100%", objectFit:"cover"}} />
                          <button onClick={() => removeSource(s.sid)} disabled={shootBusy} title="usuń"
                            style={{position:"absolute", top: 4, right: 4, width: 18, height: 18, borderRadius: 999,
                              background:"rgba(0,0,0,.55)", color:"#fff", border: 0, cursor:"pointer", fontSize: 11, lineHeight: 1, padding: 0}}>×</button>
                          <span style={{position:"absolute", bottom: 4, left: 4, fontSize: 8, color:"rgba(255,255,255,.95)",
                            textShadow:"0 1px 1px rgba(0,0,0,.5)", fontFamily:"Geist Mono"}}>{s.kind === "upload" ? "wgrane" : "render"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* picker: session / history */}
                <div style={{display:"flex", alignItems:"center", gap: 8, marginBottom: 6}}>
                  <span style={{fontSize: 11, color:"var(--ink-3)", fontFamily:"Geist Mono"}}>albo dodaj z:</span>
                  {[{id:"session", label:"Tej sesji"}, {id:"history", label:"Historii"}].map(tb => (
                    <button key={tb.id} onClick={() => setShootSourceTab(tb.id)} disabled={shootBusy}
                      style={{padding:"3px 10px", fontSize: 11, fontFamily:"Geist Mono", borderRadius: 999, border: 0, cursor:"pointer",
                        background: shootSourceTab === tb.id ? "var(--ink)" : "rgba(0,0,0,.05)",
                        color: shootSourceTab === tb.id ? "var(--paper)" : "var(--ink-3)"}}>{tb.label}</button>
                  ))}
                  {shootSourceTab === "history" && (
                    <button onClick={loadHistory} disabled={historyBusy} title="odśwież"
                      style={{padding:"3px 10px", fontSize: 11, fontFamily:"Geist Mono", borderRadius: 999, border: 0, cursor:"pointer", background:"rgba(0,0,0,.05)", color:"var(--ink-3)"}}>
                      {historyBusy ? "…" : "odśwież"}</button>
                  )}
                </div>
                {(() => {
                  let items = [];
                  if (shootSourceTab === "session") {
                    items = (gallery || []).filter(g => g && g.url).map((g, i) => ({
                      key: (g.generation_id || g.url) + "_" + i,
                      ref: g.generation_id || (g.url || "").split("/").pop(),
                      it: { generation_id: g.generation_id, image_url: g.url, color: null, material: g.material || null },
                      label: g.tag || "",
                    }));
                  } else {
                    items = (historyItems || []).map((h, i) => ({
                      key: h.generation_id || (h.image_url + "_" + i),
                      ref: h.generation_id || (h.image_url || "").split("/").pop(),
                      it: { generation_id: h.generation_id, image_url: h.image_url, color: h.color || null, material: h.material || null },
                      label: modelShort(h.model),
                    }));
                  }
                  if (shootSourceTab === "history" && historyItems === null) {
                    return <div style={{fontSize: 12, color:"var(--ink-3)", padding:"6px 0"}}>{historyBusy ? "Ładuję historię…" : "—"}</div>;
                  }
                  if (!items.length) {
                    return <div style={{fontSize: 12, color:"var(--ink-3)", padding:"6px 0"}}>
                      {shootSourceTab === "session" ? "Brak renderów w tej sesji." : "Brak renderów w historii."}
                    </div>;
                  }
                  return (
                    <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(92px, 1fr))", gap: 8, maxHeight: 210, overflow:"auto", padding: 2}}>
                      {items.map(item => {
                        const added = shootSources.some(s => s.kind === "ref" && s.ref === item.ref);
                        return (
                          <button key={item.key} disabled={shootBusy || added || shootSources.length >= 8}
                            onClick={() => addRefSource(item.it)} title={added ? "już dodane" : "dodaj"}
                            style={{position:"relative", padding: 0, border: 0, cursor: added ? "default" : "pointer",
                              borderRadius: 10, overflow:"hidden", aspectRatio:"1/1", background:"#f2f0e9",
                              outline: added ? "2.5px solid var(--ink)" : "0.5px solid rgba(0,0,0,.15)",
                              opacity: added ? 0.55 : 1}}>
                            <img src={item.it.image_url} alt="" style={{width:"100%", height:"100%", objectFit:"cover"}} />
                            <span style={{position:"absolute", top: 4, left: 4, background: added ? "var(--ink)" : "rgba(0,0,0,.5)", color:"#fff",
                              fontSize: 9, padding:"1px 6px", borderRadius: 999, fontFamily:"Geist Mono"}}>{added ? "dodane" : "+"}</span>
                          </button>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>

              {/* ============ 2 — Pary kolor + materiał ============ */}
              <div>
                <div style={{fontSize: 13, marginBottom: 6}}>2 · Pary kolor + materiał <span style={{color:"var(--ink-3)", fontFamily:"Geist Mono", fontSize: 11}}>({shootPairs.length}/8) — stosowane do każdego zdjęcia</span></div>

                {/* added pairs */}
                {shootPairs.length > 0 && (
                  <div style={{display:"flex", flexWrap:"wrap", gap: 6, marginBottom: 10}}>
                    {shootPairs.map((p, idx) => {
                      const cObj = COLORS.find(c => c.id === p.color);
                      const mObj = MATERIALS.find(m => m.id === p.material);
                      return (
                        <span key={idx} style={{display:"inline-flex", alignItems:"center", gap: 6, padding:"5px 10px",
                          borderRadius: 999, background:"var(--bg-1)", border:"1.5px solid var(--ink)", fontSize: 12}}>
                          <span style={{width: 12, height: 12, borderRadius: 999, background: cObj?.hex || "#888", border:"0.5px solid rgba(0,0,0,.18)"}}></span>
                          {cObj?.name || p.color} · {mObj?.name || p.material}
                          <button onClick={() => removePair(idx)} disabled={shootBusy} title="usuń parę"
                            style={{border: 0, background:"transparent", cursor:"pointer", color:"var(--ink-3)", fontSize: 13, lineHeight: 1, padding: 0, marginLeft: 2}}>×</button>
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* draft builder: colour + material + add */}
                <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(64px, 1fr))", gap: 6, marginBottom: 8}}>
                  {COLOR_GRID_ITEMS.map(item => {
                    if (item.type === "label") return <div key={item.key} style={GRID_LABEL_STYLE}>{item.text}</div>;
                    const c = item.c;
                    const sel = shootPairDraft.color === c.id;
                    return (
                      <button key={c.id} onClick={() => setShootPairDraft(d => ({ ...d, color: c.id, ...(c.material ? { material: c.material } : {}) }))} disabled={shootBusy}
                        title={c.name}
                        style={{position:"relative", padding: 0, border: 0, cursor:"pointer", borderRadius: 9, overflow:"hidden",
                          aspectRatio:"1/1", background: c.hex,
                          outline: sel ? "2.5px solid var(--ink)" : "0.5px solid rgba(0,0,0,.15)", outlineOffset: sel ? 1 : 0}}>
                        <span style={{position:"absolute", bottom: 3, left: 3, right: 3, fontSize: 8, color:"rgba(255,255,255,.95)",
                          textShadow:"0 1px 1px rgba(0,0,0,.4)", fontFamily:"Geist Mono", textAlign:"left"}}>{c.name}</span>
                      </button>
                    );
                  })}
                </div>
                <div style={{display:"flex", flexWrap:"wrap", gap: 6, alignItems:"center"}}>
                  {MATERIALS.map(m => {
                    const sel = shootPairDraft.material === m.id;
                    return (
                      <button key={m.id} type="button" onClick={() => setShootPairDraft(d => ({ ...d, material: m.id }))} disabled={shootBusy}
                        style={{padding:"6px 12px", borderRadius: 999, fontSize: 12.5, lineHeight: 1.2,
                          border: sel ? "1.5px solid var(--ink)" : "1px solid var(--line-2)",
                          background: sel ? "var(--bg-1)" : "transparent", cursor:"pointer", fontWeight: sel ? 600 : 400}}>
                        {m.name}
                      </button>
                    );
                  })}
                  <button onClick={addPair} disabled={shootBusy || !shootPairDraft.color || !shootPairDraft.material || shootPairs.length >= 8}
                    style={{marginLeft: 4, padding:"6px 14px", borderRadius: 999, border: 0, fontSize: 12, fontWeight: 600,
                      background:"var(--ink)", color:"var(--paper)", cursor:"pointer",
                      opacity: (!shootPairDraft.color || !shootPairDraft.material || shootPairs.length >= 8) ? 0.5 : 1}}>
                    + Dodaj parę
                  </button>
                </div>
              </div>

              {/* ============ Submit ============ */}
              <div style={{display:"flex", alignItems:"center", gap: 12, paddingTop: 2}}>
                <button onClick={handleGenerateGrid} disabled={shootBusy || !shootSources.length || !shootPairs.length}
                  style={{display:"flex", alignItems:"center", gap: 10, padding:"11px 18px", borderRadius: 999,
                    background:"var(--ink)", color:"var(--paper)", border: 0, cursor: shootBusy ? "wait" : "pointer",
                    fontSize: 13, letterSpacing:"-0.005em",
                    opacity: (!shootSources.length || !shootPairs.length || shootBusy) ? 0.5 : 1}}>
                  <span style={{display:"inline-flex"}}>{Ic.sparkle}</span>
                  <span>{shootBusy ? "Generuję…" : "Generuj warianty"}</span>
                  <span style={{fontFamily:"Geist Mono", fontSize: 11, background:"rgba(255,255,255,.10)", padding:"3px 8px", borderRadius: 999, color:"rgba(255,255,255,.75)"}}>
                    {shootSources.length}×{shootPairs.length} = {shootSources.length * shootPairs.length} · ${shootGridCost}
                  </span>
                </button>
                {shootError && <ErrorCard info={shootError} onRetry={handleGenerateGrid} onFixKey={() => setShowKeyEdit(true)} compact />}
              </div>

              {/* Live progress bar — fills as tiles stream back */}
              {shootProgress && (
                <div style={{display:"flex", flexDirection:"column", gap: 8, padding: 12, background:"rgba(0,0,0,.04)", borderRadius: 10}}>
                  <div style={{display:"flex", alignItems:"center", justifyContent:"space-between", gap: 10, fontSize: 12}}>
                    <span style={{display:"flex", alignItems:"center", gap: 8}}>
                      <span className="ico">{Ic.sparkle}</span>
                      {shootBusy
                        ? "Generuję warianty — pierwsze efekty pojawiają się na bieżąco, daj mi chwilę…"
                        : "Gotowe"}
                    </span>
                    <span style={{fontFamily:"Geist Mono", color:"var(--ink-3)"}}>
                      {shootProgress.done}/{shootProgress.total} gotowe · {Math.floor(shootElapsed)}s
                    </span>
                  </div>
                  <div style={{height: 6, borderRadius: 999, background:"rgba(0,0,0,.08)", overflow:"hidden"}}>
                    <div style={{height:"100%", borderRadius: 999, background:"var(--ink)",
                      width: (shootProgress.total ? Math.round(100 * shootProgress.done / shootProgress.total) : 0) + "%",
                      transition:"width .3s ease"}}></div>
                  </div>
                </div>
              )}

              {/* ============ Wyniki — pogrupowane po zdjęciu ============ */}
              {shootGrid && (
                <div style={{display:"flex", flexDirection:"column", gap: 18}}>
                  {!shootBusy && <div style={{fontSize: 12, color:"var(--ink-3)"}}>Gotowe · ${shootGrid.total_cost?.toFixed(3)} łącznie</div>}
                  {shootGrid.sources.map(group => {
                    const src = shootSources.find(s => s.sid === group.sid);
                    return (
                      <div key={group.sid} style={{display:"flex", flexDirection:"column", gap: 8}}>
                        <div style={{display:"flex", alignItems:"center", gap: 10}}>
                          <div style={{width: 44, height: 44, borderRadius: 8, overflow:"hidden", background:"#f2f0e9", flexShrink: 0, border:"0.5px solid rgba(0,0,0,.12)"}}>
                            {(src?.url || group.source_url) && <img src={src?.url || group.source_url} alt="" style={{width:"100%", height:"100%", objectFit:"cover"}} />}
                          </div>
                          <div style={{fontSize: 11, fontFamily:"Geist Mono", color:"var(--ink-3)"}}>
                            {group.source_kind === "upload" ? "Wgrane zdjęcie" : "Render"}
                            {group.error && <span style={{color:"#c0392b"}}> · {group.error}</span>}
                          </div>
                        </div>
                        <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(170px, 1fr))", gap: 10}}>
                          {(group.variants || []).map((v, i) => {
                            const cObj = COLORS.find(c => c.id === v.color);
                            const vMatObj = MATERIALS.find(m => m.id === v.material);
                            const regenKey = group.sid + "|" + v.color + "|" + (v.material || "");
                            const regening = !!shootRegen[regenKey];
                            const RegenBtn = (
                              <button onClick={() => src && regenerateTile(src, v.color, v.material)} disabled={regening || !src}
                                title="Wygeneruj ten kafelek ponownie"
                                style={{display:"inline-flex", alignItems:"center", gap: 4, fontSize: 10, fontFamily:"Geist Mono",
                                  color:"var(--ink)", border: 0, cursor: regening ? "wait" : "pointer", padding:"3px 7px",
                                  borderRadius: 999, background:"rgba(0,0,0,.06)"}}>
                                {regening ? "…" : "↻"} regeneruj
                              </button>
                            );
                            if (v.pending) {
                              return (
                                <div key={i} style={{display:"flex", flexDirection:"column", gap: 6, background:"#fff", borderRadius: 10, overflow:"hidden", border:"0.5px solid rgba(0,0,0,.08)"}}>
                                  <div style={{aspectRatio:"4/3", background:"#f2f0e9", position:"relative", display:"flex", alignItems:"center", justifyContent:"center"}}>
                                    <span className="ico" style={{opacity: .45}}>{Ic.sparkle}</span>
                                  </div>
                                  <div style={{padding:"6px 10px", display:"flex", alignItems:"center", gap: 6}}>
                                    <span style={{width: 12, height: 12, borderRadius: 999, flexShrink: 0, background: cObj?.hex || "#888", border:"0.5px solid rgba(0,0,0,.18)"}}></span>
                                    <span style={{fontSize: 11, fontFamily:"Geist", color:"var(--ink-3)", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>
                                      {cObj?.name || v.color}<span style={{marginLeft: 4}}>· {vMatObj?.name || v.material} · renderuję…</span>
                                    </span>
                                  </div>
                                </div>
                              );
                            }
                            if (v.error) {
                              return (
                                <div key={i} style={{padding: 10, borderRadius: 10, fontSize: 11, background:"rgba(192,57,43,.08)", color:"#c0392b",
                                  display:"flex", flexDirection:"column", gap: 6}}>
                                  <div style={{fontWeight: 600}}>{cObj?.name || v.color} · {vMatObj?.name || v.material}</div>
                                  <div>{v.error}</div>
                                  <div>{RegenBtn}</div>
                                </div>
                              );
                            }
                            const slug = fileSlug(st.product, cObj?.fabricCode || v.color, v.material);
                            const ext = (v.image_url.split(".").pop() || "png").split("?")[0];
                            const dlName = `nano-sofa-${slug}.${ext}`;
                            return (
                              <div key={i} style={{display:"flex", flexDirection:"column", gap: 6, background:"#fff", borderRadius: 10, overflow:"hidden", border:"0.5px solid rgba(0,0,0,.08)"}}>
                                <div style={{aspectRatio:"4/3", background:"#f2f0e9", position:"relative", opacity: regening ? 0.5 : 1}}>
                                  <img src={v.image_url} alt={v.color} style={{position:"absolute", inset: 0, width:"100%", height:"100%", objectFit:"cover"}} />
                                </div>
                                <div style={{padding:"6px 10px", display:"flex", alignItems:"center", justifyContent:"space-between", gap: 6}}>
                                  <div style={{display:"flex", alignItems:"center", gap: 6, minWidth: 0, flex: 1}}>
                                    <span style={{width: 12, height: 12, borderRadius: 999, flexShrink: 0, background: cObj?.hex || "#888", border:"0.5px solid rgba(0,0,0,.18)"}}></span>
                                    <span style={{fontSize: 11, fontFamily:"Geist", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis"}}>
                                      {cObj?.name || v.color}<span style={{color:"var(--ink-3)", marginLeft: 4}}>· {vMatObj?.name || v.material}</span>
                                    </span>
                                  </div>
                                </div>
                                <div style={{padding:"0 10px 8px", display:"flex", alignItems:"center", justifyContent:"space-between", gap: 6}}>
                                  {RegenBtn}
                                  <a href={v.image_url} download={dlName} title={"Pobierz " + ext.toUpperCase()}
                                    style={{display:"inline-flex", alignItems:"center", gap: 4, fontSize: 10, fontFamily:"Geist Mono",
                                      color:"var(--ink)", textDecoration:"none", padding:"3px 7px", borderRadius: 999, background:"rgba(0,0,0,.04)"}}>
                                    <span style={{display:"inline-flex", transform:"rotate(180deg)"}}>{Ic.upload}</span>
                                    {ext.toUpperCase()}
                                  </a>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {generating && (() => {
            const p50 = eta.p50_s || 12;
            const p90 = eta.p90_s || p50 * 2;
            const over = genElapsed > p90;
            const pct = Math.min(genElapsed / p50, 0.97) * 100;
            const phase =
              genElapsed < 2 ? "Przygotowuję prompt…" :
              genElapsed < p50 * 0.7 ? "Generuję obraz…" :
              over ? "Trwa dłużej niż zwykle — czekam na model…" :
              "Finalizuję render…";
            return (
              <div className="gen-overlay">
                <div className="gen-card">
                  <div className="lead">
                    <span className="ico">{Ic.sparkle}</span>
                    {phase}
                  </div>
                  <div className="gen-bar">
                    <div style={over ? undefined : { width: pct + "%", transition: "width .3s linear" }}></div>
                  </div>
                  <div className="meta">
                    {modelShort(st.model)} · {st.aspect} · {st.res.split(" ")[0]} · {genElapsed.toFixed(0)} s
                    {over ? "" : ` / ~${Math.round(p50)} s`}
                    {eta.source === "measured" ? " · zmierzone" : ""}
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
      </section>

      {/* ============= RIGHT — scrolling form ============= */}
      <section className="form-pane">
        {isLab ? (
          <PageIntro eyebrow={<>Lab · generator OpenAI · eksperyment · <a href="/help" target="_blank" rel="noopener">instrukcja ↗</a></>}>
            Ten sam przebieg co w Zdjęciach: tło, produkt, wykończenie. Renderuje GPT Image 2.5 przez OpenAI Images API
            albo przez OpenRouter (wybór w ustawieniach technicznych), a zdjęcie bazowe, komplet referencji tkaniny
            i plamka koloru idą jako obrazy edycji. Warianty i fotosesja też; wyniki lądują w Porównywarce obok Gemini.
          </PageIntro>
        ) : (
          <PageIntro eyebrow={<>Zdjęcia · brand image studio · <a href="/help" target="_blank" rel="noopener">instrukcja ↗</a></>}>
            Najpierw tło, potem produkt i wykończenie. Tło katalogowe blokuje światło i obiektyw,
            więc nic nie konkuruje z profilem; wnętrze i własne zdjęcie zostawiają kamerę Tobie.
          </PageIntro>
        )}

        <nav className="workflow-strip" aria-label="Etapy konfiguracji">
          {[
            { num:"01", title:"Tło", meta: bgObj?.name || "—", target:"section-01", done:true },
            { num:"02", title:"Produkt", meta: st.uploaded ? "Zdjęcie gotowe" : "Dodaj zdjęcie", target:"section-02", done:st.uploaded },
            { num:"03", title:"Wykończenie", meta:`${colorObj?.name || "Kolor"} · ${matObj?.name || "Tkanina"}`, target:"section-03", done:true },
          ].map(step => (
            <button type="button" key={step.num} className={step.done ? "done" : ""}
              onClick={() => document.getElementById(step.target)?.scrollIntoView({behavior:"smooth", block:"start"})}>
              <span className="workflow-num">{step.done ? "✓" : step.num}</span>
              <span><strong>{step.title}</strong><small>{step.meta}</small></span>
            </button>
          ))}
        </nav>

        {/* API key banner — sticks until a key is entered. Inline so it can't be missed. */}
        {!activeKey && (
          <div className="api-banner">
            <div className="api-banner-head">
              <div className="api-banner-eyebrow">krok zerowy</div>
              <div className="api-banner-title serif">{`Wklej swój klucz ${keyName} API, żeby zacząć`}</div>
              <div className="api-banner-help">
                {labViaOpenRouter ? (
                  <>Klucz przechowujemy tylko w Twojej przeglądarce (localStorage); serwer przekazuje go wyłącznie do
                  openrouter.ai przy każdym renderze i nie zapisuje. Pobierz klucz z {" "}
                  <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">openrouter.ai/settings/keys</a>.</>
                ) : isLab ? (
                  <>Klucz przechowujemy tylko w Twojej przeglądarce (localStorage); serwer przekazuje go wyłącznie do
                  api.openai.com przy każdym renderze i nie zapisuje. Pobierz klucz z {" "}
                  <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com/api-keys</a>.</>
                ) : (
                  <>Klucz przechowujemy tylko w Twojej przeglądarce (localStorage). Nie wysyłamy go nigdzie poza
                  wywołaniem do Google przy każdym renderze. Pobierz klucz z {" "}
                  <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">aistudio.google.com/app/apikey</a>.</>
                )}
              </div>
            </div>
            <div className="api-banner-form">
              <input
                autoFocus
                type="password"
                className="input"
                placeholder={!isLab ? "AIza..." : labViaOpenRouter ? "sk-or-..." : "sk-..."}
                onChange={e => setActiveKey(e.target.value)}
                style={{flex:1, fontFamily:"Geist Mono", fontSize: 13}}
              />
            </div>
          </div>
        )}

        {/* Technical output settings stay available, but no longer lead the workflow. */}
        <AdvancedSection title="Ustawienia techniczne"
          summary={`${modelShort(st.model)}${labViaOpenRouter ? " · openrouter" : ""}${isLab && quality ? " · " + quality : ""} · ${st.aspect} · ${st.res.split(" ")[0]}`}
          help={isLab
            ? "Model GPT Image, jakość, proporcje i rozdzielczość. Flare: domyślny, szybszy; Sunburst: ściślejsza kontrola edycji. Wersje „· OpenRouter” to te same modele płacone kluczem OpenRouter — GPT Image bez wyboru rozdzielczości (rozmiar domyślny dostawcy). Nano Banana 2.1 · OpenRouter to model Google'a z pełnym planem referencji i rozdzielczością 1K / 2K / 4K. Jakości xhigh / max są wyraźnie droższe — koszt liczony z tokenów po renderze."
            : "Model, proporcje i rozdzielczość. Nano Banana 2.1 jest polecanym modelem do codziennej pracy (4K, 14 referencji); Pro wybierz dla najbardziej wymagającej zgodności marki. Modele oznaczone jako wycofywane zostają tylko dla starych presetów."}>
          <div className="out-grid">
            <div>
              <div className="field-lbl">model</div>
              <select className="select" value={st.model} onChange={e => set({ model: e.target.value })}>
                {serverConfig.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.label} · {m.max_resolution === "auto" ? "rozmiar domyślny" : `do ${m.max_resolution || "1K"}`} · {m.max_refs} ref.
                  </option>
                ))}
              </select>
            </div>
            {(modelObj?.qualities || []).length > 0 && (
              <div>
                <div className="field-lbl">jakość</div>
                <select className="select" value={quality} onChange={e => setQuality(e.target.value)}>
                  {modelObj.qualities.map(q => <option key={q} value={q}>{q}</option>)}
                </select>
              </div>
            )}
            <div>
              <div className="field-lbl">proporcje</div>
              <select className="select" value={st.aspect} onChange={e => set({ aspect: e.target.value })}>
                <option>4:3</option><option>3:2</option><option>1:1</option><option>16:9</option>
                <option value="4:5">4:5 — Instagram feed</option>
                <option value="9:16">9:16 — Instagram Stories</option>
              </select>
            </div>
            <div>
              <div className="field-lbl">rozdz.</div>
              <select className="select" value={(st.res || "").split(" ")[0]}
                      onChange={e => set({ res: e.target.value })}>
                {(modelObj?.resolutions || ["1K"]).map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              <div style={{fontSize:10, color:"var(--ink-3)", marginTop:4, fontFamily:"Geist Mono"}}>
                limit modelu: {modelObj?.max_resolution || "1K"} · {modelObj?.max_refs || 3} ref.
              </div>
            </div>
            <div>
              <div className="field-lbl">seed</div>
              <input className="input" placeholder="losowy" value={st.seed} onChange={e => set({ seed: e.target.value })} />
            </div>
            <div>
              <div className="field-lbl">format pliku</div>
              <select className="select" value={st.outputFormat} onChange={e => set({ outputFormat: e.target.value })}>
                <option value="jpg">JPG — mały plik (zalecane)</option>
                <option value="webp">WebP — najmniejszy, z alfą</option>
                <option value="png">PNG — bezstratny, duży</option>
              </select>
            </div>
            {st.outputFormat !== "png" && (
              <div>
                <div className="field-lbl">jakość · {st.outputQuality}</div>
                <input type="range" min="40" max="100" step="1" value={st.outputQuality}
                       onChange={e => set({ outputQuality: parseInt(e.target.value, 10) || 82 })}
                       style={{width:"100%"}} />
                <div style={{fontSize:10, color:"var(--ink-3)", marginTop:4, fontFamily:"Geist Mono"}}>
                  niżej = mniejszy plik
                </div>
              </div>
            )}
          </div>
        </AdvancedSection>

        <BackgroundSection st={st} set={set} bgObj={bgObj} bgLocked={bgLocked}
          pickBackground={pickBackground} setLockBackground={setLockBackground} />

        {/* 02 — photo */}
        <Section num="02" title="Zdjęcie bazowe" summary={st.uploaded ? "wgrane · " + st.kind : "wymagane"}
          help="Punkt startowy modelu. Jasne, neutralne tło daje najlepszy rendering. Wybór typu zmienia listę rozmiarów.">
          <input ref={fileRef} type="file" accept="image/*" style={{display:"none"}}
                 onChange={e => onPickBase(e.target.files && e.target.files[0])} />
          <div className={"up-row " + (st.uploaded ? "has" : "")}
               onClick={() => fileRef.current && fileRef.current.click()}
               onDragOver={e => e.preventDefault()}
               onDrop={e => { e.preventDefault(); onPickBase(e.dataTransfer.files && e.dataTransfer.files[0]); }}>
            <div className={"up-thumb " + (st.uploaded ? "has" : "")}>
              {st.uploaded && st.basePreviewUrl
                ? <img src={st.basePreviewUrl} alt="" style={{width:"100%", height:"100%", objectFit:"cover", borderRadius:"inherit"}} />
                : Ic.upload}
            </div>
            <div className="up-body">
              <div className="lead">{st.uploaded ? st.baseFileName : "Upuść zdjęcie tutaj"}</div>
              <div className="help">{st.uploaded ? fmtSize(st.baseFileSize) + " · gotowe do generowania" : "lub kliknij, JPG / PNG / WEBP, max 12 MB"}</div>
              <div className="up-tags">
                {st.uploaded ? (
                  <>
                    <span className="up-tag">{(st.baseFile?.type || "image").replace("image/","")}</span>
                    <span className="up-tag ok">wgrane</span>
                  </>
                ) : (
                  <>
                    <span className="up-tag">JPG</span>
                    <span className="up-tag">≥ 1024 px</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="type-seg">
            <div className={"opt " + (st.kind === "sofa" ? "sel" : "")} onClick={() => set({ kind: "sofa" })}>
              <span className="ic">{Ic.sofa}</span>
              <div><div className="nm">sofa</div><div className="ds">tapicerka, nogi, podłokietniki</div></div>
            </div>
            <div className={"opt " + (st.kind === "bed" ? "sel" : "")} onClick={() => set({ kind: "bed" })}>
              <span className="ic">{Ic.bed}</span>
              <div><div className="nm">łóżko</div><div className="ds">rama, materac, zagłówek</div></div>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <div className="field-lbl">model produktu</div>
            <input className="input" placeholder={st.kind === "bed" ? "np. Aria 160" : "np. Rima 1"}
              value={st.product} maxLength={80} onChange={e => set({ product: e.target.value })} />
            <div style={{fontSize: 11, color: "var(--ink-3)", marginTop: 4}}>
              Zapisywany w metadanych i nazwie pobranego pliku razem z kodem tkaniny — nie wpływa na prompt.
            </div>
          </div>

        </Section>

        {/* 02 — color */}
        <Section num="03" title="Kolor tapicerki"
          summary={st.color === "custom" ? ("własny" + (st.colorCustomHex ? " · " + st.colorCustomHex : " opis")) : colorObj?.name}
          help="Wybierz preset albo zdefiniuj własny kolor — opisem słownym, dokładnym HEX-em lub oboma naraz. Modele rozpoznają nazwy z naszej palety najwierniej.">
          <div className="swatches">
            {COLOR_GROUPS.map(c => (
              <div key={c.id} className={"sw " + (st.color === c.id ? "sel" : "")} onClick={() => set({ color: c.id })}
                title={c.covers ? `${c.name} — obejmuje tkaniny: ${c.covers}` : c.name}>
                <div className="sw-fill" style={{ background: c.hex }}></div>
                <div className="sw-name">{c.name}</div>
                <div className="sw-hex">{c.hex}</div>
              </div>
            ))}
            <div className={"sw custom " + (st.color === "custom" ? "sel" : "")} onClick={() => set({ color: "custom" })}>
              <div className="sw-fill" style={st.colorCustomHex ? { background: st.colorCustomHex } : undefined}>{st.colorCustomHex ? "" : "+"}</div>
              <div className="sw-name">własny</div>
              <div className="sw-hex">{st.colorCustomHex || "opis / HEX"}</div>
            </div>
          </div>
          {COLLECTIONS.filter(col => col.codes.length).map(col => {
            const colMat = MATERIALS.find(m => m.id === col.material);
            return (
              <div key={col.id} style={{ marginTop: 12 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600 }}>{col.name}</span>
                  {colMat && <span style={{ fontSize: 11, color: "var(--ink-3)" }}>kolekcja · {colMat.name} (wybór ustawia materiał)</span>}
                </div>
                <div className="swatches">
                  {col.codes.map(c => (
                    <div key={c.id} className={"sw " + (st.color === c.id ? "sel" : "")}
                      onClick={() => set({ color: c.id, ...(c.material ? { mat: c.material } : {}) })}
                      title={c.hexVerified ? c.name : `${c.name} — HEX przybliżony (z grupy TreeTale); wpisz dokładny w Katalogu`}>
                      <div className="sw-fill" style={{ background: c.hex, position: "relative" }}>
                        {!c.hexVerified && <span style={{ position: "absolute", top: 3, right: 5, fontSize: 10, color: "rgba(255,255,255,.9)", textShadow: "0 1px 1px rgba(0,0,0,.5)", fontFamily: "Geist Mono" }}>≈</span>}
                      </div>
                      <div className="sw-name">{c.name}</div>
                      <div className="sw-hex">{c.hex}</div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
          {st.color === "custom" && (
            <div style={{ marginTop: 10 }}>
              <textarea className="input"
                placeholder="np. ciepła szałwia z szarym podtonem, lekko stonowana"
                value={st.colorCustom}
                onChange={e => set({ colorCustom: e.target.value })} />
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
                <input type="color"
                  value={st.colorCustomHex || "#EFEFEE"}
                  onChange={e => set({ colorCustomHex: e.target.value.toUpperCase() })}
                  style={{ width: 42, height: 32, padding: 0, border: "1px solid var(--line, #ccc)", borderRadius: 6, background: "none", cursor: "pointer" }} />
                <input type="text" className="input" style={{ width: 120, fontFamily: "Geist Mono, monospace" }}
                  placeholder="#RRGGBB (opcja)"
                  value={st.colorCustomHex}
                  onChange={e => {
                    const v = e.target.value.trim().toUpperCase();
                    if (v === "" || /^#?[0-9A-F]{0,6}$/.test(v)) set({ colorCustomHex: v && !v.startsWith("#") ? "#" + v : v });
                  }} />
                {st.colorCustomHex && (
                  <button type="button"
                    style={{ fontSize: 11, padding: "4px 10px", border: "1px solid var(--line, #ccc)", borderRadius: 6, background: "transparent", cursor: "pointer", color: "var(--ink-3, #888)" }}
                    onClick={() => set({ colorCustomHex: "" })}>wyczyść HEX</button>
                )}
              </div>
            </div>
          )}
        </Section>

        {/* 03 — material */}
        <Section num="04" title="Materiał" summary={matObj?.name + (st.matNotes ? " · z notatką" : "")}
          help="Zamknięta lista — to materiały, które model odwzorowuje wiarygodnie. Notatki o teksturze (poniżej) doprecyzowują finish.">
          <div className="mat-grid" style={{ "--mat-color": (st.color === "custom" ? "#B7A689" : (colorObj?.hex || "#B7A689")) }}>
            {MATERIALS.map(m => {
              const refs = catalogRefs[m.id] || {};
              const refCount = ["macro", "left", "right", "behavior", "application"].filter(k => refs[k]).length;
              return (
                <div key={m.id} className={"mat " + (st.mat === m.id ? "sel" : "")} onClick={() => set({ mat: m.id })}
                  title={refCount ? `${refCount} zdjęć referencyjnych w katalogu — model dostaje prawdziwą fakturę` : "Brak zdjęć referencyjnych — tylko opis tekstowy. Dodaj je w zakładce Katalog."}>
                  <div className={"mat-tex " + m.tex} style={{ position: "relative" }}>
                    <span style={{ position: "absolute", top: 5, right: 6, fontSize: 9, fontFamily: "Geist Mono", padding: "1px 5px", borderRadius: 999,
                      background: refCount ? "rgba(26,27,25,.78)" : "rgba(255,255,255,.75)", color: refCount ? "#fff" : "var(--ink-3)" }}>
                      {refCount ? `ref ×${refCount}` : "tekst"}
                    </span>
                  </div>
                  <div className="mat-meta">
                    <div className="mat-name">{m.name}</div>
                    <div className="mat-prop">{m.prop} · <span className="mat-finish">{m.finish}</span></div>
                  </div>
                </div>
              );
            })}
          </div>
          <textarea className="input" style={{ marginTop: 10 }}
            placeholder="opcjonalnie: gęste pętelki bouclé, dłuższy włos przy oparciu"
            value={st.matNotes}
            onChange={e => set({ matNotes: e.target.value })} />
        </Section>

        {/* 04 — configuration */}
        <Section num="05" title="Konfiguracja" summary={sizeObj?.name + " · " + sizeObj?.dim}
          help={st.kind === "bed" ? "Rozmiar materaca." : "Liczba miejsc — zmienia proporcje całej sceny."}>
          <div className="size-rail">
            {sizes.map(s => (
              <div key={s.id} className={"size-pill " + (st.size === s.id ? "sel" : "")} onClick={() => set({ size: s.id })}>
                <span>{s.name}</span>
                <span className="dim">{s.dim}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* 05 — legs */}
        <Section num="06" title="Nogi"
          summary={st.kind === "bed"
            ? (st.bedLegs ? (LEGS.find(l => l.id === st.legs)?.name || "na nóżkach") : "bez nóżek")
            : (LEGS.find(l => l.id === st.legs)?.name)}
          help={st.kind === "bed"
            ? "Łóżka domyślnie stoją na cokole (bez nóżek). Zaznacz, jeśli Twoje łóżko ma widoczne nóżki, i wybierz ich typ."
            : "Domyślnie zachowujemy nogi z bazy. Wybierz inne tylko jeśli celowo chcesz je zmienić."}>
          {st.kind === "bed" && (
            <label className="check" style={{ marginBottom: 12 }}>
              <input type="checkbox" checked={st.bedLegs} onChange={e => set({ bedLegs: e.target.checked })} />
              <span className="box"></span>
              <span>Łóżko na nóżkach (pokaż nóżki)</span>
            </label>
          )}
          <div className={"legs-rail " + (bedLegsHidden ? "disabled" : "")}>
            {LEGS.map(l => (
              <div key={l.id} className={"leg " + (st.legs === l.id ? "sel" : "")} onClick={() => set({ legs: l.id })}>
                <div className="glyph"><LegGlyph id={l.id} /></div>
                <div className="nm">{l.name}</div>
              </div>
            ))}
          </div>
        </Section>

        <CameraSection st={st} set={set} bgLocked={bgLocked} lensObj={lensObj} camObj={camObj} matchedPreset={matchedPreset} baseCamLocked={baseCamLocked} />

        <ReferencesSection st={st} set={set} bgLocked={bgLocked} modelObj={modelObj}
          refFileRef={refFileRef} refSlotRef={refSlotRef} onPickRef={onPickRef} clearRef={clearRef}
          fmtSize={fmtSize} budget={budget} />

        <BeddingSection st={st} set={set} />

        {/* end */}
        {genError && (
          <ErrorCard info={genError} onRetry={handleGenerate} onFixKey={() => setShowKeyEdit(true)} />
        )}

        {/* Presets — save the whole config (except base image, key, seed) and
            re-apply it to any other photo. Stored in the browser; export/import
            for backup or sharing. */}
        <div className="presets">
          <span className="presets-label">Presety</span>
          <select className="select presets-select" value={selectedPreset}
            onChange={e => { const v = e.target.value; setSelectedPreset(v); if (v) applyPreset(v); }}>
            <option value="">— wczytaj preset —</option>
            {presets.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
          <button type="button" className="preset-btn primary" onClick={savePreset}>Zapisz bieżące</button>
          <button type="button" className="preset-btn" disabled={!selectedPreset}
            onClick={() => { deletePreset(selectedPreset); setSelectedPreset(""); }}>Usuń</button>
          <button type="button" className="preset-btn" disabled={!presets.length} onClick={exportPresets}>Eksport</button>
          <button type="button" className="preset-btn" onClick={() => presetFileRef.current && presetFileRef.current.click()}>Import</button>
          <input ref={presetFileRef} type="file" accept="application/json,.json" style={{ display: "none" }}
            onChange={e => { importPresets(e.target.files && e.target.files[0]); e.target.value = ""; }} />
          {presetMsg && <span className="presets-msg">{presetMsg}</span>}
        </div>

        <div className="form-foot">
          <div className="foot-summary">
            <div className="foot-lead serif">Gotowy do wygenerowania wariantu.</div>
            <div className="foot-meta">
              <span>{colorObj?.name || "—"}</span>
              <span className="dot">·</span>
              <span>{matObj?.name}</span>
              <span className="dot">·</span>
              <span>{sizeObj?.name}</span>
              <span className="dot">·</span>
              <span>{bgObj?.name}</span>
              <span className="dot">·</span>
              <span className="mono">{st.aspect} · {st.res.split(" ")[0]}</span>
            </div>
            <div className="foot-meta" style={{ marginTop: 4 }} title={budget.attached.map(r => `${r.role}: ${r.source}`).join("\n")}>
              <span className="mono">{budget.attached.length} {budget.attached.length === 1 ? "obraz" : budget.attached.length < 5 ? "obrazy" : "obrazów"} do modelu</span>
              <span className="dot">·</span>
              <span>{budget.attached.map(r => r.label).join(", ")}</span>
              {budget.dropped.length > 0 && <span style={{ color: "var(--warn, #a33a2e)" }}> · {budget.dropped.length} ponad limit modelu</span>}
            </div>
          </div>
          <div className="foot-actions">
            {/* Background lock — appears once at least one render exists.
                When ON, the next Generate re-uses that render's image as the
                packshot SCENE reference so the backdrop stays pixel-stable
                across angle / lens / color changes. */}
            {gallery.length > 0 && !bgLocked && (
              <label title="Generuj i Warianty użyją ostatniego renderu jako sceny — kąt i kolor mogą się zmieniać, pomieszczenie zostaje. Model wie, że to render produktu, nie pusta plansza."
                style={{
                  display:"inline-flex", alignItems:"center", gap: 6,
                  padding:"6px 10px", borderRadius: 999,
                  border: lockBackground ? "1.5px solid var(--ink)" : "1px solid var(--line-2)",
                  background: lockBackground ? "var(--bg-1)" : "transparent",
                  fontSize: 11.5, fontFamily: "Geist Mono", cursor: "pointer",
                  whiteSpace: "nowrap",
                }}>
                <input type="checkbox" checked={lockBackground}
                  onChange={e => setLockBackground(e.target.checked)}
                  style={{margin:0}} />
                <span>{lockBackground ? "🔒 tło z ostatniego renderu" : "tło z ostatniego renderu"}</span>
              </label>
            )}
            <button className="copy" onClick={() => {
              navigator.clipboard?.writeText(JSON.stringify(jsonPayload, null, 2));
            }}>
              <span>{Ic.copy}</span> kopiuj JSON
            </button>
            <button className="foot-gen" onClick={handleGenerate}>
              <span className="ico">{Ic.sparkle}</span>
              <span>Generuj wariant</span>
              <span className="cost">${cost}</span>
              <span className="kbd">⌘↵</span>
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}

function Root() {
  // Stage mock-up geometry only (never posted); the tweaks panel that used
  // to edit it was a dead control for the render and is gone.
  const t = TWEAK_DEFAULTS;
  if (CATALOG_MISSING) return <CatalogMissing />;
  return <App t={t} mode={PAGE_MODE} />;
}

createRoot(document.getElementById("root")).render(<Root />);
