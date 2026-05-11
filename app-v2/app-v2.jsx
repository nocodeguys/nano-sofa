/* global React, ReactDOM, Ic, NS_DATA */
const { useState, useMemo, useRef, useEffect } = React;
const { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS, ENVIRONMENTS,
        LENSES, TIMES_OF_DAY, SHADOWS } = NS_DATA;

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
    env: "scandi", envFile: null, envNote: "", envMode: "reference",
    refs: [null, null, null],
    model: "gemini-3.1-flash-image-preview", aspect: "4:3", res: "1K", seed: "",
  });
  const set = patch => setSt(s => ({ ...s, ...patch }));

  const fileRef = useRef(null);
  const envFileRef = useRef(null);
  const onPickBase = (file) => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    set({ baseFile: file, baseFileName: file.name, baseFileSize: file.size, basePreviewUrl: url, uploaded: true });
  };
  const fmtSize = (b) => b < 1024*1024 ? (b/1024).toFixed(0) + " KB" : (b/1024/1024).toFixed(1) + " MB";

  const [stageTab, setStageTab] = useState("mockup");
  const [copied, setCopied] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [gallery, setGallery] = useState([]); // {url, color, tag, cost}
  const [activeGallery, setActiveGallery] = useState(-1);

  // Color-variant set state. variantColors is the user's multi-pick of color
  // ids (first = anchor). variantSet is the result strip after the server
  // returns { anchor, variants[] } from /api/generate-set.
  const [variantColors, setVariantColors] = useState([]);   // English color ids
  const [variantSet, setVariantSet]       = useState(null); // { anchor, variants, total_cost }
  const [variantBusy, setVariantBusy]     = useState(false);
  const [variantError, setVariantError]   = useState("");

  const colorObj = useMemo(() => COLORS.find(c => c.id === st.color), [st.color]);
  const matObj   = useMemo(() => MATERIALS.find(m => m.id === st.mat), [st.mat]);
  const sizes    = st.kind === "bed" ? SIZES_BED : SIZES_SOFA;
  const sizeObj  = useMemo(() => sizes.find(s => s.id === st.size) || sizes[0], [sizes, st.size]);
  const camObj   = useMemo(() => CAMERAS.find(c => c.id === st.cam), [st.cam]);
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
      camera: camObj?.id,
      lens: lensObj?.id || st.lens,
      time_of_day: todObj?.id || st.tod,
      shadows: shadowObj?.id || st.shadow,
    },
    references: st.refs.filter(Boolean),
    output: {
      model: st.model,
      aspect: st.aspect,
      resolution: (st.res || "").split(" ")[0],
      seed: st.seed || null,
    },
  }), [st, colorObj, matObj, sizeObj, envObj, camObj, lensObj, todObj, shadowObj]);
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
    if (!apiKey.trim()) { setGenError("Wklej klucz Gemini API u góry sceny."); setShowKeyEdit(true); return; }
    if (!st.baseFile) { setGenError("Wgraj zdjęcie bazowe (sekcja 02)."); return; }

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
    fd.append("env", st.env || "");
    fd.append("env_note", st.envNote || "");
    fd.append("env_mode", st.envMode || "");
    fd.append("model", st.model);
    fd.append("aspect", st.aspect);
    fd.append("res", st.res);
    fd.append("seed", st.seed || "");
    fd.append("base_image", st.baseFile);
    if (st.envFile && st.envFile instanceof File) {
      fd.append("scene_image", st.envFile);
    }

    setGenerating(true);
    try {
      const r = await fetch("/api/generate", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok || data.error) {
        setGenError(data.error || `Błąd serwera (${r.status})`);
      } else {
        setGallery(g => [
          { url: data.image_url, color: colorObj?.hex || "#5C7A56", tag: "v" + (g.length + 1), cost: data.cost },
          ...g,
        ]);
        setActiveGallery(0);
      }
    } catch (e) {
      setGenError(String(e && e.message ? e.message : e));
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

  const handleGenerateSet = async () => {
    setVariantError("");
    setVariantSet(null);
    if (!apiKey.trim()) { setVariantError("Wklej klucz Gemini API u góry sceny."); setShowKeyEdit(true); return; }
    if (!st.baseFile)   { setVariantError("Wgraj zdjęcie bazowe (sekcja 02)."); return; }
    if (variantColors.length < 2) { setVariantError("Wybierz co najmniej 2 kolory."); return; }

    const fd = new FormData();
    fd.append("api_key", apiKey.trim());
    fd.append("kind", st.kind);
    fd.append("colors_csv", variantColors.join(","));
    fd.append("color_custom", st.colorCustom || "");
    fd.append("mat", st.mat);
    fd.append("mat_notes", st.matNotes || "");
    fd.append("size", st.size);
    fd.append("legs", st.legs);
    fd.append("cam", st.cam);
    fd.append("lens", st.lens);
    fd.append("tod", st.tod);
    fd.append("shadow", st.shadow);
    fd.append("env", st.env || "");
    fd.append("env_note", st.envNote || "");
    fd.append("env_mode", st.envMode || "");
    fd.append("model", st.model);
    fd.append("aspect", st.aspect);
    fd.append("res", st.res);
    fd.append("seed", st.seed || "");
    fd.append("base_image", st.baseFile);
    if (st.envFile && st.envFile instanceof File) fd.append("scene_image", st.envFile);

    setVariantBusy(true);
    try {
      const r = await fetch("/api/generate-set", { method: "POST", body: fd });
      const data = await r.json();
      if (!r.ok || data.error) {
        setVariantError(data.error || `Błąd serwera (${r.status})`);
      } else {
        setVariantSet(data);
      }
    } catch (e) {
      setVariantError(String(e && e.message ? e.message : e));
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
            if (activeImg) {
              const tag = activeImg.tag || ("v" + (activeGallery + 1));
              const slug = [colorObj?.id, matObj?.id, envObj?.id].filter(Boolean).join("-");
              const ext = (activeImg.url.split(".").pop() || "png").split("?")[0];
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
                     title="Pobierz PNG"
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
                    <span>Pobierz PNG</span>
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
              {/* Locked-setup summary — keep on one line; no wrap into tabs row */}
              <div style={{
                display:"flex", flexWrap:"wrap", alignItems:"baseline",
                gap: "4px 10px", fontSize: 11,
                color:"var(--ink-3)", fontFamily:"Geist Mono",
                lineHeight: 1.5,
              }}>
                <span style={{color:"var(--ink-4, #888)"}}>Zablokowane:</span>
                <span><b style={{color:"var(--ink)"}}>{matObj?.name}</b></span>
                <span>· {sizeObj?.name} ({sizeObj?.dim})</span>
                <span>· {envObj?.name}</span>
                <span>· {camObj?.name}</span>
                <span>· {lensObj?.name?.split(" — ")[0]}</span>
                <span>· {todObj?.name?.split(" — ")[0]}</span>
                <span>· {st.model.includes("pro") ? "pro" : "flash 3.1"}</span>
              </div>

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
                  <div style={{color:"var(--danger, #c0392b)", fontSize: 11}}>
                    {variantError}
                  </div>
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
                      if (v.error) {
                        return (
                          <div key={i} style={{
                            padding: 12, borderRadius: 10, fontSize: 11,
                            background: "rgba(192, 57, 43, 0.08)", color: "#c0392b",
                          }}>
                            <div style={{fontWeight: 600}}>{cObj?.name || v.color}</div>
                            <div style={{marginTop: 4}}>{v.error}</div>
                          </div>
                        );
                      }
                      const slug = [v.color, matObj?.id, envObj?.id].filter(Boolean).join("-");
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
                            <div style={{display:"flex", alignItems:"center", gap: 6}}>
                              <span style={{width: 12, height: 12, borderRadius: 999,
                                            background: cObj?.hex || "#888",
                                            border:"0.5px solid rgba(0,0,0,.18)"}}></span>
                              <span style={{fontSize: 11, fontFamily:"Geist"}}>{cObj?.name || v.color}</span>
                            </div>
                            <a href={v.image_url} download={dlName} title="Pobierz PNG"
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
        <Section num="08" title="Kamera i światło" summary={camObj?.name + " · " + (lensObj?.name?.split(" — ")[0] || "—")}
          help="Wybór sceny ustawia oświetlenie i ogniskową. Trzy listy poniżej dostrajają detal.">
          <div className="cam-grid">
            {CAMERAS.map(c => (
              <div key={c.id} className={"cam " + (st.cam === c.id ? "sel" : "")} onClick={() => set({ cam: c.id })}>
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
                  {Array.from({length: slotCount}).map((_, i) => (
                    <div key={i}
                      className={"ref-slot " + (st.refs[i] ? "filled" : "")}
                      onClick={() => {
                        const next = [...st.refs];
                        while (next.length < slotCount) next.push(null);
                        next[i] = next[i] ? null : ["nastrojowa.jpg", "tkanina-zbliz.jpg", "salon-ref.jpg", "ref-4.jpg", "ref-5.jpg", "ref-6.jpg"][i];
                        set({ refs: next });
                      }}>
                      {st.refs[i] ? (
                        <div>
                          <div className="fname">{st.refs[i]}</div>
                          <div className="fhint">kliknij aby usunąć</div>
                        </div>
                      ) : (
                        <div>
                          <div style={{ fontSize: 16, marginBottom: 3 }}>+</div>
                          <div>slot {i + 1}</div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : null}
            </Section>
          );
        })()}

        {/* end */}
        {genError && (
          <div style={{margin:"0 0 14px 0", padding:"10px 14px", borderRadius:10,
                       background:"rgba(163,58,46,.08)", border:"1px solid rgba(163,58,46,.3)",
                       color:"#A33A2E", fontSize:13}}>
            {genError}
          </div>
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
