/* global React, ReactDOM, Ic, NS_DATA */
const { useState, useMemo, useRef, useEffect } = React;
const { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS, ENVIRONMENTS,
        LENSES, TIMES_OF_DAY, SHADOWS,
        SHOT_TYPES, DETAIL_REGIONS_FABRIC, DETAIL_REGIONS_CORNER,
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
function mkErr(message, code = "VALIDATION") {
  return { message, code, retryable: false };
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
  "stageVignette": true,
  "stageZoom": 100,
  "showFloorTag": true,
  "showVariantRail": false,
  "fabAlign": "center"
}/*EDITMODE-END*/;

const API_KEY_STORAGE = "nano-sofa-v2-api-key";

// Szybki preset → seeded structured fields. Mirrors _CAM_PRESET_TO_STRUCTURED
// in server.py (server-side fallback for legacy form posts) but adds the
// lens / DoF / detail-region that the UI also seeds on click.  Used in two
// places: the preset onClick handler (to seed st.*), and the `matchedPreset`
// memo below (to highlight the tile only while the structured fields still
// match — clicking a preset and then drifting auto-deselects the tile).
const CAM_PRESET_DEFAULTS = {
  studio: { shot: "hero",          yaw: "34_left",  height: "eye",      lens: "50mm_natural",  dof: "standard" },
  lounge: { shot: "hero",          yaw: "34_right", height: "eye",      lens: "50mm_natural",  dof: "standard" },
  loft:   { shot: "hero",          yaw: "34_left",  height: "eye",      lens: "35mm_wide",     dof: "standard" },
  detail: { shot: "detail_fabric", yaw: "front",    height: "eye",      lens: "100mm_macro",   dof: "macro_shallow", detailRegion: "weave" },
  eye:    { shot: "hero",          yaw: "front",    height: "eye",      lens: "50mm_natural",  dof: "standard" },
  top:    { shot: "hero",          yaw: "front",    height: "overhead", lens: "50mm_natural",  dof: "standard" },
};

function App({ t }) {
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(API_KEY_STORAGE, apiKey); } catch {}
  }, [apiKey]);
  // Open the key field automatically on first load when no key is set.
  const [showKeyEdit, setShowKeyEdit] = useState(() => {
    try { return !(localStorage.getItem(API_KEY_STORAGE) || ""); } catch { return true; }
  });

  // Server-driven config: models + per-model constraints (max_refs, resolutions).
  // Falls back to a single Flash entry if the request fails so the UI still loads.
  const [serverConfig, setServerConfig] = useState({
    models: [{ id: "gemini-2.5-flash-image", label: "gemini-2.5-flash-image", tier: "flash",
               max_refs: 3, resolutions: ["1K"] }],
    default_model: "gemini-2.5-flash-image",
  });
  useEffect(() => {
    fetch("/api/config")
      .then(r => r.ok ? r.json() : null)
      .then(cfg => { if (cfg && cfg.models && cfg.models.length) setServerConfig(cfg); })
      .catch(() => {});
  }, []);

  const [st, setSt] = useState({
    uploaded: false, baseFile: null, baseFileName: "", baseFileSize: 0, basePreviewUrl: null,
    alpha: false, kind: "sofa",
    color: "saliw", colorCustom: "",
    mat: "boucle", matNotes: "",
    size: "3",
    legs: "keep",
    cam: "studio", lens: "50mm_natural", tod: "noon_neutral", shadow: "soft_diffuse",
    // Structured camera controls (section 08). When `shot` is "", the server
    // derives shot/yaw/height from the `cam` preset for back-compat. Once
    // the user touches any of these chips/selects we send explicit values.
    shot: "hero", yaw: "34_left", height: "eye", dof: "standard",
    detailRegion: "weave",
    env: "scandi", envFile: null, envNote: "", envMode: "reference",
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
    model: "gemini-3.1-flash-image-preview", aspect: "4:3", res: "1K", seed: "",
    outputFormat: "jpg", outputQuality: 82,
  });
  const set = patch => setSt(s => ({ ...s, ...patch }));

  const fileRef = useRef(null);
  const envFileRef = useRef(null);
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
  // When true, the next /api/generate call attaches the most recent gallery
  // image as scene_image — locking the backdrop pixel-perfectly across
  // re-renders. Same mechanism the Warianty tab uses for cross-variant
  // background consistency. Disabled until at least one render exists.
  const [lockBackground, setLockBackground] = useState(false);
  const [genError, setGenError] = useState("");
  const [gallery, setGallery] = useState([]); // {url, color, tag, cost}
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

  // Photoshoot session state. Sources are the user's uploaded angle photos;
  // each has a role: "packshot" | "lifestyle" | "skip". Backdrop is the
  // locked cyclorama profile id. Result is { packshot[], lifestyle[], errors[] }.
  const [shootSources, setShootSources] = useState([]);  // [{file, role, previewUrl, name}]
  const [shootBackdrop, setShootBackdrop] = useState("cyclorama_warm");
  const [shootLifestyleEnv, setShootLifestyleEnv] = useState("scandi");
  const [shootResult, setShootResult] = useState(null);
  const [shootBusy, setShootBusy] = useState(false);
  const [shootError, setShootError] = useState("");

  const colorObj = useMemo(() => COLORS.find(c => c.id === st.color), [st.color]);
  const matObj   = useMemo(() => MATERIALS.find(m => m.id === st.mat), [st.mat]);
  const sizes    = st.kind === "bed" ? SIZES_BED : SIZES_SOFA;
  const sizeObj  = useMemo(() => sizes.find(s => s.id === st.size) || sizes[0], [sizes, st.size]);
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
  const envObj   = useMemo(() => ENVIRONMENTS.find(e => e.id === st.env), [st.env]);
  const lensObj   = useMemo(() => LENSES.find(l => l.id === st.lens),         [st.lens]);
  const todObj    = useMemo(() => TIMES_OF_DAY.find(t => t.id === st.tod),    [st.tod]);
  const shadowObj = useMemo(() => SHADOWS.find(s => s.id === st.shadow),      [st.shadow]);

  // Single source of truth for the public JSON contract — the same shape is
  // used by the JSON tab preview, the JSON-tab Copy button, and the footer
  // "kopiuj JSON" button. Every value is an English stable id, a hex color,
  // a measurement string, or null. No Polish strings, no UI-only state.
  const jsonPayload = useMemo(() => ({
    product: { type: st.kind, base: st.uploaded ? st.baseFileName || "base.jpg" : null },
    variant: {
      color: st.color === "custom"
        ? { custom: st.colorCustom }
        : { id: colorObj?.id, hex: colorObj?.hex },
      material: { id: matObj?.id, notes: st.matNotes || null },
      size: { id: sizeObj?.id, dim: sizeObj?.dim },
      legs: st.kind === "bed" ? "disabled_for_bed" : st.legs,
    },
    scene: {
      environment: envObj?.id,
      // `camera_preset` is the *matched* preset (null when the user has
      // drifted from a clicked preset) — not the last preset id they
      // clicked. This makes the JSON honest about current state.
      camera_preset: matchedPreset,
      shot: st.shot,
      // Subject region — populated only for shot types that use one
      // (close_up / detail_fabric / detail_corner). Keeps the JSON clean
      // for hero/wide/three_quarter/cropped shots.
      detail_region: (st.shot === "close_up" || st.shot === "detail_fabric" || st.shot === "detail_corner")
        ? st.detailRegion
        : null,
      yaw: st.yaw,
      camera_height: st.height,
      depth_of_field: st.dof,
      lens: lensObj?.id || st.lens,
      time_of_day: todObj?.id || st.tod,
      shadows: shadowObj?.id || st.shadow,
    },
    references: st.refs.filter(Boolean).map(r => r.name || "reference"),
    output: {
      model: st.model,
      aspect: st.aspect,
      resolution: (st.res || "").split(" ")[0],
      seed: st.seed || null,
    },
  }), [st, colorObj, matObj, sizeObj, envObj, camObj, lensObj, todObj, shadowObj, matchedPreset]);
  const modelObj = useMemo(
    () => serverConfig.models.find(m => m.id === st.model) || serverConfig.models[0],
    [serverConfig, st.model],
  );

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
  }, [serverConfig, st.model]);

  const cost = useMemo(() => {
    const base = st.model.includes("pro") ? 0.12 : 0.03;
    const refMult = 1 + st.refs.filter(Boolean).length * 0.15;
    const r = (st.res || "").split(" ")[0];
    const resMult = r === "4K" ? 2.4 : r === "2K" ? 1.6 : 1;
    return (base * refMult * resMult).toFixed(3);
  }, [st.model, st.refs, st.res]);

  const handleGenerate = async () => {
    setGenError("");
    if (!apiKey.trim()) { setGenError(mkErr("Wklej klucz Gemini API u góry sceny.", "MISSING_API_KEY")); setShowKeyEdit(true); return; }
    if (!st.baseFile) { setGenError(mkErr("Wgraj zdjęcie bazowe (sekcja 02).", "MISSING_BASE_IMAGE")); return; }

    const fd = new FormData();
    fd.append("api_key", apiKey.trim());
    fd.append("kind", st.kind);
    fd.append("color", st.color);
    fd.append("color_custom", st.colorCustom || "");
    fd.append("mat", st.mat);
    fd.append("mat_notes", st.matNotes || "");
    fd.append("size", st.size);
    fd.append("legs", st.legs);
    fd.append("cam", st.cam);
    fd.append("lens", st.lens);
    fd.append("tod", st.tod);
    fd.append("shadow", st.shadow);
    fd.append("shot", st.shot || "");
    fd.append("yaw", st.yaw || "");
    fd.append("height", st.height || "");
    fd.append("dof", st.dof || "");
    fd.append("detail_region", st.detailRegion || "");
    fd.append("env", st.env || "");
    fd.append("env_note", st.envNote || "");
    fd.append("env_mode", st.envMode || "");
    fd.append("model", st.model);
    fd.append("aspect", st.aspect);
    fd.append("res", st.res);
    fd.append("seed", st.seed || "");
    fd.append("output_format", st.outputFormat || "jpg");
    fd.append("output_quality", String(st.outputQuality || 82));
    fd.append("base_image", st.baseFile);
    // Background lock: when active, fetch the most recent gallery render and
    // attach it as scene_image. The server's packshot SCENE block instructs
    // Gemini to copy backdrop tone, top-light gradient, and contact-shadow
    // quality from the attached cyclorama reference, so the second render
    // lands on the same backdrop pixels as the first. Overrides any
    // env=custom upload — the lock takes priority.
    let backgroundLocked = false;
    if (lockBackground && gallery[0]?.url) {
      try {
        const prev = await fetch(gallery[0].url);
        const blob = await prev.blob();
        const ext = (gallery[0].url.split(".").pop() || "png").split("?")[0];
        const file = new File([blob], `prev-render.${ext}`, { type: blob.type || "image/png" });
        fd.append("scene_image", file);
        backgroundLocked = true;
      } catch (e) {
        // If fetch fails fall back to the user's env upload (if any).
        console.warn("Background lock failed, continuing without it:", e);
      }
    }
    if (!backgroundLocked && st.envFile && st.envFile instanceof File) {
      fd.append("scene_image", st.envFile);
    }
    // Section 09 "Referencje" — moodboard uploads. Send each picked file as a
    // separate `references` entry so FastAPI receives them as list[UploadFile].
    const hasAnyRef = st.refs.some(r => r && r.file instanceof File);
    for (const r of st.refs) {
      if (r && r.file instanceof File) fd.append("references", r.file);
    }
    // Reference-lock: makes the uploaded reference the source of truth for
    // camera/lighting/scene; suppresses the wizard's camera + scene blocks.
    // Only meaningful when at least one reference is present.
    if (hasAnyRef && st.refsLock) fd.append("refs_lock", "1");
    if (st.preserveBaseCamera) fd.append("preserve_base", "1");
    if (st.kind === "bed") {
      fd.append("bedding", st.bedding || "");
      fd.append("bedding_custom", st.beddingCustom || "");
      fd.append("throw", st.throw || "");
      fd.append("tidy", st.tidy || "");
      fd.append("density", st.density || "");
      fd.append("accents", (st.accents || []).join(","));
      fd.append("bed_note", st.bedNote || "");
    }

    setGenerating(true);
    try {
      const r = await fetch("/api/generate", { method: "POST", body: fd });
      let data = null;
      try { data = await r.json(); } catch { /* non-JSON body (proxy error page) */ }
      if (!r.ok || !data || data.error) {
        setGenError(errorFromResponse(r, data));
      } else {
        setGallery(g => [
          { url: data.image_url, color: colorObj?.hex || "#5C7A56", tag: "v" + (g.length + 1), cost: data.cost },
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

  // when size list changes (sofa↔bed), correct st.size
  useEffect(() => {
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
    const base = st.model.includes("pro") ? 0.12 : 0.067;
    const r = (st.res || "").split(" ")[0];
    const resMult = r === "4K" ? 2.4 : r === "2K" ? 1.6 : 1;
    // Each non-anchor variant has 1 extra reference (the anchor png), so apply 1.15× ref multiplier.
    const anchorCost = base * resMult;
    const variantCost = base * 1.15 * resMult;
    return (anchorCost + variantCost * Math.max(0, variantColors.length - 1)).toFixed(3);
  }, [st.model, st.res, variantColors.length]);

  // -------- Fotosesja (photoshoot session) handlers --------
  const onShootPickFiles = (files) => {
    const arr = Array.from(files || []);
    if (!arr.length) return;
    setShootSources(prev => {
      const next = [...prev];
      arr.forEach((f, i) => {
        // Default the first 6 to packshot, anything after to lifestyle.
        const idx = next.length;
        next.push({
          file: f,
          role: idx < 6 ? "packshot" : "lifestyle",
          previewUrl: URL.createObjectURL(f),
          name: f.name,
        });
      });
      return next;
    });
  };

  const setShootSourceRole = (i, role) => {
    setShootSources(prev => prev.map((s, idx) => idx === i ? { ...s, role } : s));
  };
  const removeShootSource = (i) => {
    setShootSources(prev => {
      const removed = prev[i];
      if (removed?.previewUrl) try { URL.revokeObjectURL(removed.previewUrl); } catch {}
      return prev.filter((_, idx) => idx !== i);
    });
  };

  const shootCounts = useMemo(() => {
    const p = shootSources.filter(s => s.role === "packshot").length;
    const l = shootSources.filter(s => s.role === "lifestyle").length;
    return { packshot: p, lifestyle: Math.min(l, 2), skipped: shootSources.filter(s => s.role === "skip").length, lifestyleExtra: Math.max(0, l - 2) };
  }, [shootSources]);

  const shootCost = useMemo(() => {
    const base = st.model.includes("pro") ? 0.12 : 0.067;
    const r = (st.res || "").split(" ")[0];
    const resMult = r === "4K" ? 2.4 : r === "2K" ? 1.6 : 1;
    // Packshot variants 2..N add ~15% for the swatch reference image; lifestyle variant 2 adds ~15% for scene ref.
    const packshotAnchor = base * resMult;
    const packshotVariant = base * 1.15 * resMult;
    const lifestyleAnchor = base * resMult;
    const lifestyleVariant = base * 1.15 * resMult;
    const total = (
      (shootCounts.packshot > 0 ? packshotAnchor : 0)
      + packshotVariant * Math.max(0, shootCounts.packshot - 1)
      + (shootCounts.lifestyle > 0 ? lifestyleAnchor : 0)
      + lifestyleVariant * Math.max(0, shootCounts.lifestyle - 1)
    );
    return total.toFixed(3);
  }, [st.model, st.res, shootCounts]);

  const handleGenerateShoot = async () => {
    setShootError("");
    setShootResult(null);
    if (!apiKey.trim()) { setShootError(mkErr("Wklej klucz Gemini API u góry sceny.", "MISSING_API_KEY")); setShowKeyEdit(true); return; }
    const usable = shootSources.filter(s => s.role !== "skip");
    if (usable.length === 0) { setShootError(mkErr("Dodaj co najmniej jedno zdjęcie źródłowe.", "MISSING_SOURCES")); return; }
    if (usable.length > 10) { setShootError(mkErr("Limit sesji: max 10 zdjęć źródłowych.", "TOO_MANY_SOURCES")); return; }

    const fd = new FormData();
    fd.append("api_key", apiKey.trim());
    fd.append("kind", st.kind);
    fd.append("color", st.color);
    fd.append("color_custom", st.colorCustom || "");
    fd.append("mat", st.mat);
    fd.append("mat_notes", st.matNotes || "");
    fd.append("size", st.size);
    fd.append("legs", st.legs);
    fd.append("cam", st.cam);
    fd.append("lens", st.lens);
    fd.append("tod", st.tod);
    fd.append("shadow", st.shadow);
    fd.append("shot", st.shot || "");
    fd.append("yaw", st.yaw || "");
    fd.append("height", st.height || "");
    fd.append("dof", st.dof || "");
    fd.append("detail_region", st.detailRegion || "");
    fd.append("backdrop", shootBackdrop);
    fd.append("lifestyle_env", shootLifestyleEnv);
    fd.append("env_note", st.envNote || "");
    fd.append("model", st.model);
    fd.append("aspect", st.aspect);
    fd.append("res", st.res);
    fd.append("seed", st.seed || "");
    fd.append("output_format", st.outputFormat || "jpg");
    fd.append("output_quality", String(st.outputQuality || 82));
    // Sources + roles arrays are positionally paired on the server side.
    const roles = [];
    for (const s of shootSources) {
      if (s.role === "skip") continue;
      // Cap lifestyle uses to 2 — the rest become packshot extras.
      let r = s.role;
      if (r === "lifestyle" && roles.filter(x => x === "lifestyle").length >= 2) r = "packshot";
      fd.append("sources", s.file);
      roles.push(r);
    }
    fd.append("source_roles_csv", roles.join(","));

    setShootBusy(true);
    try {
      const resp = await fetch("/api/generate-photoshoot", { method: "POST", body: fd });
      let data = null;
      try { data = await resp.json(); } catch { /* non-JSON body */ }
      if (!resp.ok || !data || data.error) {
        setShootError(errorFromResponse(resp, data));
      } else {
        setShootResult(data);
      }
    } catch (e) {
      setShootError(errorFromException(e));
    } finally {
      setShootBusy(false);
    }
  };

  const handleGenerateSet = async () => {
    setVariantError("");
    setVariantSet(null);
    if (!apiKey.trim()) { setVariantError(mkErr("Wklej klucz Gemini API u góry sceny.", "MISSING_API_KEY")); setShowKeyEdit(true); return; }
    if (!st.baseFile)   { setVariantError(mkErr("Wgraj zdjęcie bazowe (sekcja 02).", "MISSING_BASE_IMAGE")); return; }
    if (variantColors.length < 2) { setVariantError(mkErr("Wybierz co najmniej 2 kolory.", "TOO_FEW_COLORS")); return; }

    const fd = new FormData();
    fd.append("api_key", apiKey.trim());
    fd.append("kind", st.kind);
    fd.append("colors_csv", variantColors.join(","));
    // Empty materials_csv → server reuses single `mat` for every variant.
    fd.append("materials_csv", variantMaterials.join(","));
    fd.append("color_custom", st.colorCustom || "");
    fd.append("mat", st.mat);
    fd.append("mat_notes", st.matNotes || "");
    fd.append("size", st.size);
    fd.append("legs", st.legs);
    fd.append("cam", st.cam);
    fd.append("lens", st.lens);
    fd.append("tod", st.tod);
    fd.append("shadow", st.shadow);
    fd.append("shot", st.shot || "");
    fd.append("yaw", st.yaw || "");
    fd.append("height", st.height || "");
    fd.append("dof", st.dof || "");
    fd.append("detail_region", st.detailRegion || "");
    fd.append("env", st.env || "");
    fd.append("env_note", st.envNote || "");
    fd.append("env_mode", st.envMode || "");
    // Bed-styling block. Same payload shape as /api/generate so the variant
    // set inherits the textile arrangement chosen in section 10.
    if (st.kind === "bed") {
      fd.append("bedding", st.bedding || "");
      fd.append("bedding_custom", st.beddingCustom || "");
      fd.append("throw", st.throw || "");
      fd.append("tidy", st.tidy || "");
      fd.append("density", st.density || "");
      fd.append("accents", (st.accents || []).join(","));
      fd.append("bed_note", st.bedNote || "");
    }
    fd.append("model", st.model);
    fd.append("aspect", st.aspect);
    fd.append("res", st.res);
    fd.append("seed", st.seed || "");
    fd.append("output_format", st.outputFormat || "jpg");
    fd.append("output_quality", String(st.outputQuality || 82));
    fd.append("base_image", st.baseFile);
    if (st.envFile && st.envFile instanceof File) fd.append("scene_image", st.envFile);

    setVariantBusy(true);
    try {
      const r = await fetch("/api/generate-set", { method: "POST", body: fd });
      let data = null;
      try { data = await r.json(); } catch { /* non-JSON body */ }
      if (!r.ok || !data || data.error) {
        setVariantError(errorFromResponse(r, data));
      } else {
        setVariantSet(data);
      }
    } catch (e) {
      setVariantError(errorFromException(e));
    } finally {
      setVariantBusy(false);
    }
  };

  return (
    <div className="shell">
      {/* ============= LEFT — sticky stage ============= */}
      <section className="stage-pane">
        <div className="stage-mark">
          <span className="glyph"></span>
          <span className="name">Nano Sofa <span className="light">studio</span></span>
        </div>
        {showKeyEdit ? (
          <input
            autoFocus
            type="password"
            className="input"
            placeholder="AIza..."
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            onBlur={() => setShowKeyEdit(false)}
            onKeyDown={e => { if (e.key === "Enter" || e.key === "Escape") setShowKeyEdit(false); }}
            style={{position:"absolute", top:18, right:18, width: 260, padding: "6px 10px", fontSize: 12, fontFamily: "Geist Mono"}}
          />
        ) : (
          <div className="stage-status" onClick={() => setShowKeyEdit(true)} style={{cursor:"pointer"}} title="kliknij aby wkleić / zmienić klucz">
            <span className="dot" style={apiKey ? {} : {background:"#B5663A"}}></span>
            <span>{apiKey ? `klucz aktywny · ••${apiKey.slice(-4)}` : "wklej klucz Gemini"}</span>
          </div>
        )}

        <div className="stage-tabs">
          <button className={stageTab === "mockup" ? "on" : ""} onClick={() => setStageTab("mockup")}>Mockup</button>
          <button className={stageTab === "json" ? "on" : ""} onClick={() => setStageTab("json")}>JSON</button>
          <button className={stageTab === "variants" ? "on" : ""} onClick={() => setStageTab("variants")}>Warianty</button>
          <button className={stageTab === "photoshoot" ? "on" : ""} onClick={() => setStageTab("photoshoot")}>Fotosesja</button>
        </div>

        <div className="stage-canvas" style={{
          background: envObj?.grad,
          "--stage-zoom": (t.stageZoom / 100),
          "--vignette-opacity": t.stageVignette ? 0.18 : 0,
        }}>
          {stageTab === "mockup" && (() => {
            const showGen = activeGallery >= 0 && gallery[activeGallery] && gallery[activeGallery].url;
            if (showGen) {
              return <img src={gallery[activeGallery].url} alt="rendering"
                          style={{position:"absolute", inset:"6% 6% 14% 6%", width:"88%", height:"80%", objectFit:"contain"}} />;
            }
            return (
              <div className="sofa" style={{
                "--mat-color": colorObj?.hex || "#6F8C68",
                width: t.sofaWidth + "%",
                bottom: t.sofaBottom + "%",
                aspectRatio: `${t.sofaAspect} / 1`,
                borderRadius: `${t.sofaRadius}px ${t.sofaRadius}px 8px 8px`,
                boxShadow: `0 28px 50px -22px rgba(0,0,0,${t.shadowStrength/100}), inset 0 -8px 0 -3px rgba(0,0,0,.10)`,
              }}>
                <div className={"fabric-overlay " + (matObj?.tex || "")}></div>
                <div className="sofa-legs">
                  {Array.from({ length: 4 }).map((_, i) => <span key={i} />)}
                </div>
              </div>
            );
          })()}

          {stageTab === "mockup" && t.showFloorTag && <div className="stage-summary-top">
            <div className="line"><span className="k">kolor</span><span className="v serif">{colorObj?.name || "—"}</span></div>
            <div className="line"><span className="k">tkanina</span><span className="v serif">{matObj?.name || "—"}</span></div>
            <div className="line"><span className="k">format</span><span className="v serif">{sizeObj?.name} · {sizeObj?.dim}</span></div>
            <div className="line"><span className="k">scena</span><span className="v serif">{envObj?.name}</span></div>
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
              const slug = [colorObj?.id, matObj?.id, envObj?.id].filter(Boolean).join("-");
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
              // Clear the stage-mark (y≈22-50) and stage-tabs (y≈56-89) which
              // sit on top of the canvas. Start below them.
              position:"absolute", top: 100, left: 0, right: 0, bottom: 0,
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
                    <span>· {envObj?.name}</span>
                    <span>· {shotObj?.name || camObj?.name}</span>
                    {regionObj && <span style={{color:"var(--ink)"}}>· {regionObj.name}</span>}
                    <span>· {lensObj?.name?.split(" — ")[0]}</span>
                    <span>· {todObj?.name?.split(" — ")[0]}</span>
                    {beddingObj && <span>· {beddingObj.name}</span>}
                    <span>· {st.model.includes("pro") ? "pro" : "flash 3.1"}</span>
                  </div>
                );
              })()}

              <div>
                <div style={{fontSize: 13, marginBottom: 6}}>Wybierz kolory (pierwszy = anchor, reszta dziedziczy scenę)</div>
                <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(72px, 1fr))", gap: 8}}>
                  {COLORS.map((c, i) => {
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
                      const slug = [v.color, vMatId, envObj?.id].filter(Boolean).join("-");
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
              display:"flex", flexDirection:"column", gap: 14,
              background:"var(--paper, #f4f0e5)",
              padding: "8px 24px 24px",
              overflow:"auto",
              zIndex: 2,
            }}>
              {/* Locked-variant summary — show what's being applied to the whole session */}
              <div style={{
                display:"flex", flexWrap:"wrap", alignItems:"baseline",
                gap: "4px 10px", fontSize: 11,
                color:"var(--ink-3)", fontFamily:"Geist Mono",
                lineHeight: 1.5,
              }}>
                <span style={{color:"var(--ink-4, #888)"}}>Wariant:</span>
                <span><b style={{color:"var(--ink)"}}>{colorObj?.name || st.color}</b></span>
                <span>· <b style={{color:"var(--ink)"}}>{matObj?.name || st.mat}</b></span>
                <span>· {sizeObj?.name} ({sizeObj?.dim})</span>
                <span>· {st.model.includes("pro") ? "pro" : "flash 3.1"}</span>
                <span>· {st.aspect} · {(st.res || "").split(" ")[0]}</span>
              </div>

              {/* Backdrop + lifestyle env pickers */}
              <div style={{display:"grid", gridTemplateColumns: "1fr 1fr", gap: 10}}>
                <div>
                  <div style={{fontSize: 11, color:"var(--ink-3)", marginBottom: 4, fontFamily:"Geist Mono"}}>tło packshot (locked cyclorama)</div>
                  <select className="select" value={shootBackdrop}
                          onChange={e => setShootBackdrop(e.target.value)}
                          disabled={shootBusy}
                          style={{width:"100%"}}>
                    <option value="cyclorama_warm">Cyklorama ciepła #F4F0E5 (catalog)</option>
                    <option value="cyclorama_neutral">Cyklorama neutralna #FAFAFA (clean white)</option>
                    <option value="cyclorama_grey">Cyklorama szara #DCDCDC (packshot grey)</option>
                    <option value="cyclorama_transparent">Bez tła (alpha PNG)</option>
                  </select>
                </div>
                <div>
                  <div style={{fontSize: 11, color:"var(--ink-3)", marginBottom: 4, fontFamily:"Geist Mono"}}>scena lifestyle (1-2 zdjęć)</div>
                  <select className="select" value={shootLifestyleEnv}
                          onChange={e => setShootLifestyleEnv(e.target.value)}
                          disabled={shootBusy}
                          style={{width:"100%"}}>
                    {ENVIRONMENTS.filter(e => !e.id.startsWith("cyclorama") && !["studio_white","studio_grey","transparent","custom"].includes(e.id)).map(e =>
                      <option key={e.id} value={e.id}>{e.name}</option>
                    )}
                  </select>
                </div>
              </div>

              {/* Upload zone + thumbnails */}
              <div>
                <div style={{fontSize: 13, marginBottom: 4}}>Zdjęcia źródłowe (kąty kamery — dodaj 6-8, pierwsze 6 = packshot, ostatnie 1-2 = lifestyle)</div>
                <div style={{fontSize: 10, marginBottom: 8, color:"var(--ink-3)", fontFamily:"Geist Mono"}}>
                  <b style={{color:"var(--ink)"}}>Tło</b> = na cykloramie (packshot) ·
                  <b style={{color:"var(--ink)"}}> Pokój</b> = wnętrze lifestyle (max 2) ·
                  <b style={{color:"var(--ink)"}}> Pomiń</b> = nie używaj
                </div>
                <label style={{
                  display:"flex", alignItems:"center", justifyContent:"center",
                  padding: "16px 20px", border: "1px dashed rgba(0,0,0,.25)",
                  borderRadius: 10, cursor: shootBusy ? "not-allowed" : "pointer",
                  fontSize: 12, color:"var(--ink-3)",
                  background:"rgba(255,255,255,.5)",
                  opacity: shootBusy ? 0.6 : 1,
                }}>
                  <input type="file" accept="image/*" multiple style={{display:"none"}}
                         disabled={shootBusy}
                         onChange={e => onShootPickFiles(e.target.files)} />
                  <span style={{display:"inline-flex", marginRight: 8}}>{Ic.upload}</span>
                  Wybierz wiele zdjęć albo upuść tutaj
                </label>
                {shootSources.length > 0 && (
                  <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(120px, 1fr))", gap: 8, marginTop: 8}}>
                    {shootSources.map((s, i) => (
                      <div key={i} style={{
                        position:"relative",
                        background:"#fff", borderRadius: 10, overflow:"hidden",
                        border: "0.5px solid rgba(0,0,0,.1)",
                      }}>
                        <div style={{aspectRatio:"1/1", background:"#f2f0e9"}}>
                          <img src={s.previewUrl} alt={s.name}
                               style={{width:"100%", height:"100%", objectFit:"cover"}} />
                          <span style={{
                            position:"absolute", top: 4, left: 4,
                            background:"var(--ink)", color:"var(--paper)",
                            fontSize: 9, padding: "1px 5px", borderRadius: 999,
                            fontFamily:"Geist Mono",
                          }}>v{i + 1}</span>
                          <button onClick={() => removeShootSource(i)}
                                  disabled={shootBusy}
                                  style={{
                                    position:"absolute", top: 4, right: 4,
                                    width: 18, height: 18, borderRadius: 999,
                                    background: "rgba(0,0,0,.5)", color:"#fff",
                                    border: 0, cursor:"pointer", fontSize: 10, padding: 0, lineHeight: 1,
                                  }} title="usuń">×</button>
                        </div>
                        <div style={{padding: "5px 6px"}}>
                          <div style={{fontSize: 9, color:"var(--ink-3)", fontFamily:"Geist Mono",
                                       overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", marginBottom: 3}}
                               title={s.name}>{s.name}</div>
                          <div style={{display:"flex", gap: 2}}>
                            {[
                              {id:"packshot", label:"Tło",   title:"Tło — wariant na cykloramie (packshot)"},
                              {id:"lifestyle",label:"Pokój", title:"Pokój — wariant w wnętrzu lifestyle (max 2)"},
                              {id:"skip",     label:"Pomiń", title:"Pomiń — nie używaj tego zdjęcia"},
                            ].map(role => (
                              <button key={role.id}
                                      onClick={() => setShootSourceRole(i, role.id)}
                                      disabled={shootBusy}
                                      title={role.title}
                                      style={{
                                        flex: 1, padding: "3px 0",
                                        fontSize: 10, fontFamily:"Geist Mono",
                                        background: s.role === role.id ? "var(--ink)" : "rgba(0,0,0,.05)",
                                        color: s.role === role.id ? "var(--paper)" : "var(--ink-3)",
                                        border: 0, borderRadius: 4, cursor: "pointer",
                                      }}>{role.label}</button>
                            ))}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {shootCounts.lifestyleExtra > 0 && (
                  <div style={{fontSize: 11, color: "#c0392b", marginTop: 6}}>
                    Uwaga: tylko 2 pierwsze zdjęcia oznaczone „Pokój" zostaną wyrenderowane jako lifestyle; pozostałe {shootCounts.lifestyleExtra} → tło.
                  </div>
                )}
              </div>

              {/* Submit row */}
              <div style={{display:"flex", alignItems:"center", gap: 12, paddingTop: 4}}>
                <button onClick={handleGenerateShoot}
                        disabled={shootBusy || shootSources.length === 0}
                        style={{
                          display:"flex", alignItems:"center", gap: 10,
                          padding: "11px 18px", borderRadius: 999,
                          background: "var(--ink)", color: "var(--paper)",
                          border: 0, cursor: shootBusy ? "wait" : "pointer",
                          fontSize: 13, letterSpacing: "-0.005em",
                          opacity: (shootSources.length === 0 || shootBusy) ? 0.5 : 1,
                        }}>
                  <span style={{display:"inline-flex"}}>{Ic.sparkle}</span>
                  <span>{shootBusy ? "Generuję sesję…" : "Generuj fotosesję"}</span>
                  <span style={{
                    fontFamily:"Geist Mono", fontSize: 11,
                    background:"rgba(255,255,255,.10)", padding:"3px 8px",
                    borderRadius: 999, color:"rgba(255,255,255,.75)",
                  }}>{shootCounts.packshot} tło + {shootCounts.lifestyle} pokój · ${shootCost}</span>
                </button>
                {shootError && (
                  <ErrorCard info={shootError} onRetry={handleGenerateShoot} onFixKey={() => setShowKeyEdit(true)} compact />
                )}
              </div>

              {shootBusy && (
                <div style={{display:"flex", alignItems:"center", gap: 10, padding: 10,
                              background:"rgba(0,0,0,.04)", borderRadius: 10, fontSize: 12}}>
                  <span className="ico">{Ic.sparkle}</span>
                  <span>
                    Pass A: każdy packshot solo z lockedym tłem (cyklorama ref) · Pass B: lifestyle anchor + scene-ref dla 2. shot
                  </span>
                </div>
              )}

              {shootResult && (
                <div style={{display:"flex", flexDirection:"column", gap: 14}}>
                  <div style={{fontSize: 12, color:"var(--ink-3)"}}>
                    Sesja gotowa · ${shootResult.total_cost?.toFixed(3)} łącznie
                    {shootResult.errors?.length > 0 && ` · ${shootResult.errors.length} błędów`}
                  </div>

                  {shootResult.packshot?.length > 0 && (
                    <div>
                      <div style={{fontSize: 11, color:"var(--ink-3)", fontFamily:"Geist Mono", marginBottom: 6}}>
                        TŁO / CYKLORAMA ({shootResult.packshot.length}) — każdy ze swojego kąta źródłowego, wspólne tło z referencji
                      </div>
                      <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(180px, 1fr))", gap: 10}}>
                        {shootResult.packshot.map((r, i) => {
                          const slug = [st.color, st.mat, shootBackdrop].filter(Boolean).join("-");
                          const ext = (r.image_url.split(".").pop() || "png").split("?")[0];
                          const dlName = `nano-sofa-${r.label}-${slug}.${ext}`;
                          return (
                            <div key={i} style={{
                              display:"flex", flexDirection:"column",
                              background:"#fff", borderRadius: 10, overflow:"hidden",
                              border: "0.5px solid rgba(0,0,0,.08)",
                            }}>
                              <div style={{aspectRatio:"4/3", background:"#f2f0e9", position:"relative"}}>
                                <img src={r.image_url} alt={r.label}
                                     style={{position:"absolute", inset: 0, width:"100%", height:"100%", objectFit:"cover"}} />
                                {r.anchor && (
                                  <span style={{position:"absolute", top: 6, left: 6,
                                                background:"var(--ink)", color:"var(--paper)",
                                                fontSize: 9, padding: "2px 6px", borderRadius: 999,
                                                fontFamily:"Geist Mono"}}>anchor</span>
                                )}
                              </div>
                              <div style={{padding:"6px 10px", display:"flex", alignItems:"center", justifyContent:"space-between"}}>
                                <span style={{fontSize: 11, fontFamily:"Geist Mono"}}>{r.label}</span>
                                <a href={r.image_url} download={dlName}
                                   style={{display:"inline-flex", alignItems:"center", gap: 4,
                                           fontSize: 10, fontFamily:"Geist Mono",
                                           color:"var(--ink)", textDecoration:"none",
                                           padding:"3px 7px", borderRadius: 999, background:"rgba(0,0,0,.04)"}}>
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

                  {shootResult.lifestyle?.length > 0 && (
                    <div>
                      <div style={{fontSize: 11, color:"var(--ink-3)", fontFamily:"Geist Mono", marginBottom: 6}}>
                        POKÓJ / LIFESTYLE ({shootResult.lifestyle.length}) — wspólne wnętrze, drugi shot dziedziczy scenę z anchora
                      </div>
                      <div style={{display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(220px, 1fr))", gap: 10}}>
                        {shootResult.lifestyle.map((r, i) => {
                          const slug = [st.color, st.mat, shootLifestyleEnv].filter(Boolean).join("-");
                          const ext = (r.image_url.split(".").pop() || "png").split("?")[0];
                          const dlName = `nano-sofa-${r.label}-lifestyle-${slug}.${ext}`;
                          return (
                            <div key={i} style={{
                              display:"flex", flexDirection:"column",
                              background:"#fff", borderRadius: 10, overflow:"hidden",
                              border: "0.5px solid rgba(0,0,0,.08)",
                            }}>
                              <div style={{aspectRatio:"4/3", background:"#f2f0e9", position:"relative"}}>
                                <img src={r.image_url} alt={r.label}
                                     style={{position:"absolute", inset: 0, width:"100%", height:"100%", objectFit:"cover"}} />
                                {r.anchor && (
                                  <span style={{position:"absolute", top: 6, left: 6,
                                                background:"var(--ink)", color:"var(--paper)",
                                                fontSize: 9, padding: "2px 6px", borderRadius: 999,
                                                fontFamily:"Geist Mono"}}>anchor</span>
                                )}
                              </div>
                              <div style={{padding:"6px 10px", display:"flex", alignItems:"center", justifyContent:"space-between"}}>
                                <span style={{fontSize: 11, fontFamily:"Geist Mono"}}>{r.label}</span>
                                <a href={r.image_url} download={dlName}
                                   style={{display:"inline-flex", alignItems:"center", gap: 4,
                                           fontSize: 10, fontFamily:"Geist Mono",
                                           color:"var(--ink)", textDecoration:"none",
                                           padding:"3px 7px", borderRadius: 999, background:"rgba(0,0,0,.04)"}}>
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

                  {shootResult.errors?.length > 0 && (
                    <div>
                      <div style={{fontSize: 11, color:"#c0392b", fontFamily:"Geist Mono", marginBottom: 6}}>BŁĘDY</div>
                      <div style={{display:"flex", flexDirection:"column", gap: 4}}>
                        {shootResult.errors.map((e, i) => (
                          <div key={i} style={{fontSize: 11, color:"#c0392b", padding: "6px 10px",
                                               background:"rgba(192,57,43,.08)", borderRadius: 6}}>
                            <b>{e.label}</b> ({e.role}{e.source_filename ? `, ${e.source_filename}` : ""}): {e.error}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {generating && (
            <div className="gen-overlay">
              <div className="gen-card">
                <div className="lead">
                  <span className="ico">{Ic.sparkle}</span>
                  Renderuję wariant…
                </div>
                <div className="gen-bar"><div></div></div>
                <div className="meta">{st.model} · {st.aspect} · {st.res.split(" ")[0]} · ~12 s</div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ============= RIGHT — scrolling form ============= */}
      <section className="form-pane">
        <div className="form-intro">
          <div className="eyebrow">Studio · v2 · konfigurator</div>
          <h1>Złóż wariant zdjęcia produktu — <em>pojedynczy formularz, jeden render.</em></h1>
          <p>Wszystkie ustawienia widoczne na raz, żywy podgląd po lewej. Przewiń od góry, ustaw co chcesz, naciśnij Generuj.</p>
        </div>

        {/* API key banner — sticks until a key is entered. Inline so it can't be missed. */}
        {!apiKey && (
          <div className="api-banner">
            <div className="api-banner-head">
              <div className="api-banner-eyebrow">krok zerowy</div>
              <div className="api-banner-title serif">Wklej swój klucz Gemini API, żeby zacząć</div>
              <div className="api-banner-help">
                Klucz przechowujemy tylko w Twojej przeglądarce (localStorage). Nie wysyłamy go nigdzie poza
                wywołaniem do Google przy każdym renderze. Pobierz klucz z {" "}
                <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">aistudio.google.com/app/apikey</a>.
              </div>
            </div>
            <div className="api-banner-form">
              <input
                autoFocus
                type="password"
                className="input"
                placeholder="AIza..."
                onChange={e => setApiKey(e.target.value)}
                style={{flex:1, fontFamily:"Geist Mono", fontSize: 13}}
              />
            </div>
          </div>
        )}

        {/* 01 — output (was 09) */}
        <Section num="01" title="Wyjście" summary={`${st.model.includes("pro") ? "pro" : "flash"} · ${st.aspect} · ${st.res.split(" ")[0]}`}
          help="Model, proporcje, rozdzielczość. Flash: szybki, do 1K, max 3 referencje. Pro: do 2K, droższy 4×.">
          <div className="out-grid">
            <div>
              <div className="field-lbl">model</div>
              <select className="select" value={st.model} onChange={e => set({ model: e.target.value })}>
                {serverConfig.models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.label} {m.tier === "pro" ? "· pro" : "· flash"} · do {m.max_resolution || "1K"}
                  </option>
                ))}
              </select>
            </div>
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
        </Section>

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

          <label className="check">
            <input type="checkbox" checked={st.alpha} onChange={e => set({ alpha: e.target.checked })} />
            <span className="box"></span>
            Spłaszcz alfę do 18% szarości tła
          </label>
        </Section>

        {/* 02 — color */}
        <Section num="03" title="Kolor tapicerki" summary={st.color === "custom" ? "własny opis" : colorObj?.name}
          help="Wybierz preset lub opisz własny odcień słownie. Modele rozpoznają nazwy z naszej palety najwierniej.">
          <div className="swatches">
            {COLORS.map(c => (
              <div key={c.id} className={"sw " + (st.color === c.id ? "sel" : "")} onClick={() => set({ color: c.id })}>
                <div className="sw-fill" style={{ background: c.hex }}></div>
                <div className="sw-name">{c.name}</div>
                <div className="sw-hex">{c.hex}</div>
              </div>
            ))}
            <div className={"sw custom " + (st.color === "custom" ? "sel" : "")} onClick={() => set({ color: "custom" })}>
              <div className="sw-fill">+</div>
              <div className="sw-name">własny</div>
              <div className="sw-hex">opisz</div>
            </div>
          </div>
          {st.color === "custom" && (
            <textarea className="input" style={{ marginTop: 10 }}
              placeholder="np. ciepła szałwia z szarym podtonem, lekko stonowana"
              value={st.colorCustom}
              onChange={e => set({ colorCustom: e.target.value })} />
          )}
        </Section>

        {/* 03 — material */}
        <Section num="04" title="Materiał" summary={matObj?.name + (st.matNotes ? " · z notatką" : "")}
          help="Zamknięta lista — to materiały, które model odwzorowuje wiarygodnie. Notatki o teksturze (poniżej) doprecyzowują finish.">
          <div className="mat-grid">
            {MATERIALS.map(m => (
              <div key={m.id} className={"mat " + (st.mat === m.id ? "sel" : "")} onClick={() => set({ mat: m.id })}>
                <div className={"mat-tex " + m.tex}></div>
                <div className="mat-meta">
                  <div className="mat-name">{m.name}</div>
                  <div className="mat-prop">{m.prop}</div>
                </div>
              </div>
            ))}
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
        <Section num="06" title="Nogi" summary={st.kind === "bed" ? "wyłączone" : (LEGS.find(l => l.id === st.legs)?.name)}
          help={st.kind === "bed" ? "Dla łóżek krok jest pomijany." : "Domyślnie zachowujemy nogi z bazy. Wybierz inne tylko jeśli celowo chcesz je zmienić."}>
          <div className={"legs-rail " + (st.kind === "bed" ? "disabled" : "")}>
            {LEGS.map(l => (
              <div key={l.id} className={"leg " + (st.legs === l.id ? "sel" : "")} onClick={() => set({ legs: l.id })}>
                <div className="glyph"><LegGlyph id={l.id} /></div>
                <div className="nm">{l.name}</div>
              </div>
            ))}
          </div>
        </Section>

        {/* 06 — environment */}
        <Section num="07" title="Otoczenie" summary={envObj?.name}
          help="Scena, w której pokażemy mebel. „Bez tła” oddaje PNG z alfą. „Własne zdjęcie” pozwala wgrać Twoje wnętrze.">
          <div className="env-grid">
            {ENVIRONMENTS.map(e => (
              <div key={e.id}
                className={"env " + (st.env === e.id ? "sel " : "") + (e.checker ? "checker" : "")}
                onClick={() => set({ env: e.id })}>
                <div className="env-thumb" style={{ background: e.grad }}>
                  {!e.custom && !e.checker && (
                    <>
                      <div className="floor" style={{ background: e.acc }}></div>
                      <div className="prop"></div>
                    </>
                  )}
                  {e.custom && <div className="upload-icon">+</div>}
                </div>
                <div className="env-meta">
                  <div className="env-name">{e.name}</div>
                  <div className="env-prop">{e.prop}</div>
                </div>
              </div>
            ))}
          </div>

          {st.env === "custom" && (
            <div className="env-custom">
              <div className="head">
                <span className="ico">{Ic.upload}</span>
                <div style={{ flex: 1 }}>
                  <div className="lead">{(st.envFile && st.envFile.name) || "Wgraj zdjęcie tła"}</div>
                  <div className="sub">{st.envFile ? "kliknij aby zmienić" : "model użyje go jako referencji oświetlenia i kolorów"}</div>
                </div>
                <input
                  ref={envFileRef}
                  type="file"
                  accept="image/*"
                  style={{ display: "none" }}
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) set({ envFile: f });
                  }}
                />
                <button className="size-pill" onClick={() => {
                  if (st.envFile) { set({ envFile: null }); return; }
                  envFileRef.current?.click();
                }}>
                  {st.envFile ? "usuń" : "wybierz plik"}
                </button>
              </div>
              <div className="tri-row" style={{ marginTop: 0, gridTemplateColumns: "1fr 1fr" }}>
                <div>
                  <div className="field-lbl">notatka</div>
                  <input className="input" placeholder="np. salon na poddaszu, popołudnie"
                    value={st.envNote} onChange={e => set({ envNote: e.target.value })} />
                </div>
                <div>
                  <div className="field-lbl">tryb</div>
                  <select className="select" value={st.envMode} onChange={e => set({ envMode: e.target.value })}>
                    <option value="reference">referencja stylu</option>
                    <option value="background">jako dosłowne tło</option>
                    <option value="lighting">tylko światło / kolory</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </Section>

        {/* 07 — camera */}
        <Section num="08" title="Kamera i kadrowanie" summary={(() => {
          if (st.preserveBaseCamera) return "z bazowego zdjęcia · " + (lensObj?.name?.split(" — ")[0] || "—");
          const shotObj = SHOT_TYPES.find(s => s.id === st.shot);
          let regionTable = null;
          if (st.shot === "detail_fabric") regionTable = DETAIL_REGIONS_FABRIC;
          else if (st.shot === "detail_corner") regionTable = DETAIL_REGIONS_CORNER;
          else if (st.shot === "close_up") regionTable = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
          const regionObj = regionTable ? regionTable.find(r => r.id === st.detailRegion) : null;
          const parts = [shotObj?.name || camObj?.name];
          if (regionObj) parts.push(regionObj.name);
          parts.push(lensObj?.name?.split(" — ")[0] || "—");
          return parts.filter(Boolean).join(" · ");
        })()}
          help="Wybierz typ kadru. Dla detali makro rezygnujemy z cyklorama tła i kierujemy model na samą fakturę.">
          <label style={{
            display:"flex", alignItems:"flex-start", gap:8, marginBottom:12,
            padding:"10px 12px", border:"1px solid var(--line-2)", borderRadius:10,
            background: st.preserveBaseCamera ? "rgba(95,122,86,.06)" : "var(--bg-1)",
            cursor: st.uploaded ? "pointer" : "not-allowed",
            opacity: st.uploaded ? 1 : 0.55,
            fontSize:12.5, lineHeight:1.45,
          }}>
            <input
              type="checkbox"
              checked={st.uploaded && !!st.preserveBaseCamera}
              disabled={!st.uploaded}
              onChange={e => set({ preserveBaseCamera: e.target.checked })}
              style={{marginTop:2, flexShrink:0}} />
            <span>
              <strong style={{fontWeight:600}}>Zachowaj kąt i sylwetkę z bazowego zdjęcia</strong>
              {!st.uploaded
                ? " — wgraj najpierw zdjęcie bazowe w sekcji 02, żeby włączyć tę opcję."
                : " — kamera, kadrowanie, dystans i pozycja produktu pochodzą wtedy z bazowego zdjęcia (sekcja 02). Idealne do macro / detal crop, kiedy nie chcesz, by model „doframował” pełny produkt. Kolor, materiał, rozmiar i otoczenie nadal pochodzą z kreatora."}
            </span>
          </label>
          {/* Quick preset — clicking a tile also seeds the structured fields
              below (yaw, height, shot type, lens, DoF) so the user has a
              sensible starting point that they can then tweak. Mirrors
              _CAM_PRESET_TO_STRUCTURED in server.py. */}
          <div className="field-lbl">szybki preset</div>
          <div className="cam-grid" style={st.preserveBaseCamera ? {opacity:0.4, pointerEvents:"none"} : undefined}>
            {CAMERAS.map(c => (
              <div key={c.id} className={"cam " + (matchedPreset === c.id ? "sel" : "")} onClick={() => {
                set({ cam: c.id, ...(CAM_PRESET_DEFAULTS[c.id] || {}) });
              }}>
                <div className={"cam-render " + (c.style || "")}>
                  <div className="floor"></div>
                  <div className="obj"></div>
                </div>
                <div className="cam-meta">
                  <div className="cam-name">{c.name}</div>
                  <div className="cam-prop">{c.prop}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Shot type — primary framing intent. Detail variants suppress
              the cyclorama SCENE block server-side and emit an OOF-background
              line, so the model actually crops to the detail region instead
              of falling back to a hero packshot. */}
          <div className="field-lbl" style={{marginTop:16}}>typ kadru</div>
          <div className="cam-grid" style={{
            gridTemplateColumns: "repeat(auto-fill,minmax(150px,1fr))",
            ...(st.preserveBaseCamera ? {opacity:0.4, pointerEvents:"none"} : {}),
          }}>
            {SHOT_TYPES.map(s => (
              <div key={s.id} className={"cam " + (st.shot === s.id ? "sel" : "")} onClick={() => {
                // Shot-type picks nudge sensible defaults for lens / DoF /
                // region so the user has a reasonable starting point.
                const isDetail = s.id === "detail_fabric" || s.id === "detail_corner";
                const isCloseUp = s.id === "close_up";
                const patch = { shot: s.id };
                if (isDetail) {
                  patch.lens = (st.lens === "35mm_wide" || st.lens === "50mm_natural") ? "100mm_macro" : st.lens;
                  patch.dof = "macro_shallow";
                  if (s.id === "detail_fabric") patch.detailRegion = DETAIL_REGIONS_FABRIC.some(r => r.id === st.detailRegion) ? st.detailRegion : "weave";
                  if (s.id === "detail_corner") patch.detailRegion = DETAIL_REGIONS_CORNER.some(r => r.id === st.detailRegion) ? st.detailRegion : "arm_back_corner";
                }
                if (isCloseUp) {
                  // 85 mm short telephoto flatters the close-up framing.
                  // Don't downgrade a longer focal length the user already picked.
                  if (st.lens === "35mm_wide" || st.lens === "50mm_natural") patch.lens = "85mm_product";
                  patch.dof = "shallow";
                  const table = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
                  const stillValid = table.some(r => r.id === st.detailRegion);
                  patch.detailRegion = stillValid ? st.detailRegion : (st.kind === "bed" ? "bed_corner_head" : "sofa_corner");
                }
                set(patch);
              }}>
                <div className="cam-meta" style={{padding:"10px 12px"}}>
                  <div className="cam-name">{s.name}</div>
                  <div className="cam-prop">{s.hint}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Subject region — visible for detail and close-up shots. The
              region table is product-aware for close-up: bed → bed regions,
              sofa → sofa regions. */}
          {(() => {
            let regions = null;
            let label = "";
            if (st.shot === "detail_fabric") { regions = DETAIL_REGIONS_FABRIC; label = "obszar detalu"; }
            else if (st.shot === "detail_corner") { regions = DETAIL_REGIONS_CORNER; label = "obszar detalu"; }
            else if (st.shot === "close_up") {
              regions = st.kind === "bed" ? CLOSE_REGIONS_BED : CLOSE_REGIONS_SOFA;
              label = "obszar zbliżenia";
            }
            if (!regions) return null;
            return (
              <>
                <div className="field-lbl" style={{marginTop:12}}>{label}</div>
                <div style={{display:"flex", flexWrap:"wrap", gap:8, marginBottom:4}}>
                  {regions.map(r => (
                    <button key={r.id} type="button"
                      onClick={() => set({ detailRegion: r.id })}
                      style={{
                        padding:"6px 12px", borderRadius:8, fontSize:12.5,
                        border: st.detailRegion === r.id ? "1.5px solid var(--ink)" : "1px solid var(--line-2)",
                        background: st.detailRegion === r.id ? "var(--bg-1)" : "transparent",
                        cursor: "pointer", fontWeight: st.detailRegion === r.id ? 600 : 400,
                      }}>{r.name}</button>
                  ))}
                </div>
              </>
            );
          })()}

          {/* Yaw / height / DoF — orientation + height + aperture. Yaw and
              height are dimmed for detail shots because the macro crop fills
              the frame regardless of where the camera is yawed. */}
          <div className="tri-row" style={{marginTop:12,
            ...(st.preserveBaseCamera ? {opacity:0.4, pointerEvents:"none"} : {}),
          }}>
            <div style={(st.shot === "detail_fabric" || st.shot === "detail_corner") ? {opacity:0.45, pointerEvents:"none"} : undefined}>
              <div className="field-lbl">kąt (yaw)</div>
              <select className="select" value={st.yaw} onChange={e => set({ yaw: e.target.value })}>
                {CAMERA_YAWS.map(y => <option key={y.id} value={y.id}>{y.name}</option>)}
              </select>
            </div>
            <div style={(st.shot === "detail_fabric" || st.shot === "detail_corner") ? {opacity:0.45, pointerEvents:"none"} : undefined}>
              <div className="field-lbl">wysokość kamery</div>
              <select className="select" value={st.height} onChange={e => set({ height: e.target.value })}>
                {CAMERA_HEIGHTS.map(h => <option key={h.id} value={h.id}>{h.name}</option>)}
              </select>
            </div>
            <div>
              <div className="field-lbl">głębia ostrości</div>
              <select className="select" value={st.dof} onChange={e => set({ dof: e.target.value })}>
                {DEPTHS_OF_FIELD.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
          </div>

          <div className="tri-row">
            <div>
              <div className="field-lbl">ogniskowa</div>
              <select className="select" value={st.lens} onChange={e => set({ lens: e.target.value })}>
                {LENSES.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </div>
            <div>
              <div className="field-lbl">pora dnia</div>
              <select className="select" value={st.tod} onChange={e => set({ tod: e.target.value })}>
                {TIMES_OF_DAY.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <div className="field-lbl">cienie</div>
              <select className="select" value={st.shadow} onChange={e => set({ shadow: e.target.value })}>
                {SHADOWS.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
          </div>
        </Section>

        {/* 08 — references */}
        {(() => {
          // Base product image always occupies slot 1 → user can add up to max_refs - 1 extras.
          const maxExtras = Math.max(0, (modelObj?.max_refs || 3) - 1);
          const slotCount = Math.max(0, Math.min(maxExtras, 6));   // UI hard cap of 6 to keep layout sane
          const filled = st.refs.filter(Boolean).length;
          return (
            <Section num="09" title="Referencje"
              summary={slotCount === 0 ? "n/d" : `${filled} / ${slotCount}`}
              help={slotCount === 0
                ? "Wybrany model nie przyjmuje dodatkowych referencji — wystarczy samo zdjęcie bazowe."
                : `Maks. ${slotCount} dodatkowe obrazy dla wybranego modelu. Wybierz najtrafniejsze kadry, nie cały moodboard.`}>
              {slotCount > 0 ? (
                <div className="refs">
                  <input ref={refFileRef} type="file" accept="image/*" style={{display:"none"}}
                    onChange={e => { onPickRef(e.target.files && e.target.files[0]); e.target.value = ""; }} />
                  {Array.from({length: slotCount}).map((_, i) => {
                    const r = st.refs[i];
                    return (
                      <div key={i}
                        className={"ref-slot " + (r ? "filled" : "")}
                        title={r ? `${r.name} · ${fmtSize(r.size)} · kliknij aby zmienić` : `slot ${i + 1} — kliknij aby wgrać`}
                        onClick={() => {
                          refSlotRef.current = i;
                          refFileRef.current && refFileRef.current.click();
                        }}
                        style={r && r.previewUrl ? {
                          backgroundImage: `url(${r.previewUrl})`,
                          backgroundSize: "cover",
                          backgroundPosition: "center",
                        } : undefined}>
                        {r ? (
                          <button
                            type="button"
                            onClick={ev => { ev.stopPropagation(); clearRef(i); }}
                            title="Usuń referencję"
                            style={{
                              position:"absolute", top:4, right:4,
                              width:18, height:18, borderRadius:9,
                              border:"none", background:"rgba(0,0,0,.55)",
                              color:"#fff", fontSize:12, lineHeight:"16px",
                              cursor:"pointer", padding:0,
                            }}>×</button>
                        ) : (
                          <div>
                            <div style={{ fontSize: 16, marginBottom: 3 }}>+</div>
                            <div>slot {i + 1}</div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {slotCount > 0 ? (
                <label style={{
                  display:"flex", alignItems:"flex-start", gap:8, marginTop:10,
                  padding:"10px 12px", border:"1px solid var(--line-2)", borderRadius:10,
                  background: (filled > 0 && st.refsLock) ? "rgba(95,122,86,.06)" : "var(--bg-1)",
                  cursor: filled > 0 ? "pointer" : "not-allowed",
                  opacity: filled > 0 ? 1 : 0.55,
                  fontSize:12.5, lineHeight:1.45,
                }}>
                  <input
                    type="checkbox"
                    checked={filled > 0 && !!st.refsLock}
                    disabled={filled === 0}
                    onChange={e => set({ refsLock: e.target.checked })}
                    style={{marginTop:2, flexShrink:0}} />
                  <span>
                    <strong style={{fontWeight:600}}>Użyj referencji jako wzorca</strong>
                    {filled === 0
                      ? " — wgraj najpierw referencję w slot powyżej, żeby włączyć tę opcję."
                      : " — "}
                    {filled > 0 && (
                      <>
                        referencja staje się źródłem prawdy dla kąta kamery,
                        kadrowania, oświetlenia, cieni i sceny. Ustawienia z sekcji{" "}
                        <span style={{fontFamily:"'Geist Mono', monospace"}}>04 Ujęcie</span>{", "}
                        <span style={{fontFamily:"'Geist Mono', monospace"}}>06 Otoczenie</span>{" oraz "}
                        <span style={{fontFamily:"'Geist Mono', monospace"}}>07 Światło</span>
                        {" "}są wtedy ignorowane. Kolor, materiał, nogi i rozmiar nadal pochodzą z kreatora.
                      </>
                    )}
                  </span>
                </label>
              ) : null}
            </Section>
          );
        })()}

        {/* 10 — bed styling (only when product is a bed) */}
        {st.kind === "bed" && (() => {
          const beddingObj = BEDDING_PRESETS.find(b => b.id === st.bedding) || BEDDING_PRESETS[1];
          const tidyObj    = TIDY_LEVELS.find(t => t.id === st.tidy)        || TIDY_LEVELS[1];
          const densityObj = DENSITY_LEVELS.find(d => d.id === st.density)  || DENSITY_LEVELS[1];
          const throwObj   = THROW_PRESETS.find(t => t.id === st.throw)     || THROW_PRESETS[0];
          const accentNames = (st.accents || [])
            .map(id => BED_ACCENTS.find(a => a.id === id)?.name)
            .filter(Boolean);
          const summaryBits = [
            st.bedding === "none" ? "bez pościeli" : beddingObj?.name,
            tidyObj?.name,
            st.density !== "balanced" ? densityObj?.name : null,
            st.throw !== "none" ? throwObj?.name : null,
            accentNames.length ? `+${accentNames.length}` : null,
          ].filter(Boolean);
          const toggleAccent = (id) => {
            const cur = new Set(st.accents || []);
            cur.has(id) ? cur.delete(id) : cur.add(id);
            set({ accents: Array.from(cur) });
          };
          return (
            <Section num="10" title="Pościel i styling"
              summary={summaryBits.join(" · ")}
              help="Co leży na łóżku, jak bardzo jest pościelone i ile rzeczy ma się znaleźć w kadrze. Tylko dla łóżek — wysyłane do Gemini jako osobny blok BEDDING.">
              <div className="field-lbl">Pościel</div>
              <select className="select" value={st.bedding} onChange={e => set({ bedding: e.target.value })}>
                {BEDDING_PRESETS.map(b => <option key={b.id} value={b.id}>{b.name} — {b.prop}</option>)}
              </select>
              {st.bedding === "custom" && (
                <input className="input" placeholder="np. ciepłe wafelkowe w pasku, ecru z koronką na poszewce"
                  style={{marginTop:6}}
                  value={st.beddingCustom} onChange={e => set({ beddingCustom: e.target.value })} />
              )}

              <div className="tri-row" style={{marginTop:12}}>
                <div>
                  <div className="field-lbl">Porządek</div>
                  <select className="select" value={st.tidy} onChange={e => set({ tidy: e.target.value })}>
                    {TIDY_LEVELS.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
                <div>
                  <div className="field-lbl">Koc / narzuta</div>
                  <select className="select" value={st.throw} onChange={e => set({ throw: e.target.value })}>
                    {THROW_PRESETS.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
                <div>
                  <div className="field-lbl">Gęstość kadru</div>
                  <select className="select" value={st.density} onChange={e => set({ density: e.target.value })}>
                    {DENSITY_LEVELS.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                </div>
              </div>

              <div className="field-lbl" style={{marginTop:12}}>
                Akcenty {st.density === "minimal" && (
                  <span style={{color:"var(--ink-3)", fontWeight:400}}>(ignorowane przy gęstości minimalnej)</span>
                )}
              </div>
              <div style={{display:"flex", flexWrap:"wrap", gap:6}}>
                {BED_ACCENTS.map(a => {
                  const on = (st.accents || []).includes(a.id);
                  return (
                    <button key={a.id} type="button"
                      onClick={() => toggleAccent(a.id)}
                      style={{
                        padding:"6px 12px", borderRadius:14, fontSize:12,
                        border: on ? "1.5px solid var(--ink-2)" : "1px solid var(--line-2)",
                        background: on ? "rgba(95,122,86,.10)" : "var(--bg-1)",
                        color: on ? "var(--ink)" : "var(--ink-2)",
                        cursor: "pointer",
                      }}>
                      {on ? "✓ " : "+ "}{a.name}
                    </button>
                  );
                })}
              </div>

              <div className="field-lbl" style={{marginTop:12}}>Notatka stylingu (opcjonalnie)</div>
              <input className="input"
                placeholder='np. „kołdra złożona w trójkąt, jedna poszewka delikatnie pomięta"'
                value={st.bedNote} onChange={e => set({ bedNote: e.target.value })} />
            </Section>
          );
        })()}

        {/* end */}
        {genError && (
          <ErrorCard info={genError} onRetry={handleGenerate} onFixKey={() => setShowKeyEdit(true)} />
        )}
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
              <span>{envObj?.name}</span>
              <span className="dot">·</span>
              <span className="mono">{st.aspect} · {st.res.split(" ")[0]}</span>
            </div>
          </div>
          <div className="foot-actions">
            {/* Background lock — appears once at least one render exists.
                When ON, the next Generate re-uses that render's image as the
                packshot SCENE reference so the backdrop stays pixel-stable
                across angle / lens / color changes. */}
            {gallery.length > 0 && (
              <label title="Następna generacja użyje ostatniego renderu jako referencji tła — kąt i kolor mogą się zmieniać, tło zostaje."
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
                <span>{lockBackground ? "🔒 tło z poprzedniego" : "zablokuj tło"}</span>
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
  );
}

/* generic section wrapper */
function Section({ num, title, summary, help, children }) {
  return (
    <div className="section">
      <div className="sec-head">
        <div className="num">{num}</div>
        <div className="title serif">{title}</div>
        {summary && <div className="summary">{summary}</div>}
      </div>
      {help && <p className="sec-help">{help}</p>}
      <div className="sec-body">{children}</div>
    </div>
  );
}

function StagePaneTweaks({ t, setTweak }) {
  return (
    <TweaksPanel title="Tweaks — scena">
      <TweakSection label="Mebel">
        <TweakSlider label="Szerokość" value={t.sofaWidth} min={28} max={80} step={1} unit="%"
          onChange={v => setTweak('sofaWidth', v)} />
        <TweakSlider label="Pozycja od dołu" value={t.sofaBottom} min={10} max={50} step={1} unit="%"
          onChange={v => setTweak('sofaBottom', v)} />
        <TweakSlider label="Proporcja (szer/wys)" value={t.sofaAspect} min={1.4} max={3.6} step={0.1}
          onChange={v => setTweak('sofaAspect', v)} />
        <TweakSlider label="Zaokrąglenie" value={t.sofaRadius} min={4} max={40} step={1} unit="px"
          onChange={v => setTweak('sofaRadius', v)} />
        <TweakSlider label="Siła cienia" value={t.shadowStrength} min={0} max={60} step={2} unit="%"
          onChange={v => setTweak('shadowStrength', v)} />
      </TweakSection>
      <TweakSection label="Scena">
        <TweakToggle label="Winieta na dole" value={t.stageVignette}
          onChange={v => setTweak('stageVignette', v)} />
        <TweakToggle label="Etykieta z parametrami" value={t.showFloorTag}
          onChange={v => setTweak('showFloorTag', v)} />
        <TweakToggle label="Mini-warianty (rail)" value={t.showVariantRail}
          onChange={v => setTweak('showVariantRail', v)} />
        <TweakRadio label="Generuj — położenie" value={t.fabAlign}
          options={['left','center','right']}
          onChange={v => setTweak('fabAlign', v)} />
      </TweakSection>
    </TweaksPanel>
  );
}

function Root() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  return (
    <>
      <App t={t} />
      <StagePaneTweaks t={t} setTweak={setTweak} />
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<Root />);
