/* global React, ReactDOM, Ic, NS_DATA */
const { useState, useMemo, useRef, useEffect } = React;
const { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS, ENVIRONMENTS } = NS_DATA;

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
  const [showKeyEdit, setShowKeyEdit] = useState(false);

  const [st, setSt] = useState({
    uploaded: false, baseFile: null, baseFileName: "", baseFileSize: 0, basePreviewUrl: null,
    alpha: false, kind: "sofa",
    color: "saliw", colorCustom: "",
    mat: "boucle", matNotes: "",
    size: "3",
    legs: "keep",
    cam: "studio", lens: "50 mm — naturalna", tod: "południe — neutralne", shadow: "miękkie rozproszone",
    env: "scandi", envFile: null, envNote: "", envMode: "reference",
    refs: [null, null, null],
    model: "gemini-2.5-flash-image", aspect: "4:3", res: "1K — Flash limit", seed: "",
  });
  const set = patch => setSt(s => ({ ...s, ...patch }));

  const fileRef = useRef(null);
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

  const colorObj = useMemo(() => COLORS.find(c => c.id === st.color), [st.color]);
  const matObj   = useMemo(() => MATERIALS.find(m => m.id === st.mat), [st.mat]);
  const sizes    = st.kind === "bed" ? SIZES_BED : SIZES_SOFA;
  const sizeObj  = useMemo(() => sizes.find(s => s.id === st.size) || sizes[0], [sizes, st.size]);
  const camObj   = useMemo(() => CAMERAS.find(c => c.id === st.cam), [st.cam]);
  const envObj   = useMemo(() => ENVIRONMENTS.find(e => e.id === st.env), [st.env]);

  const cost = useMemo(() => {
    const base = st.model.includes("pro") ? 0.12 : 0.03;
    const refMult = 1 + st.refs.filter(Boolean).length * 0.15;
    const resMult = st.res.startsWith("2K") ? 1.6 : 1;
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
        </div>

        <div className="stage-canvas" style={{
          background: envObj?.grad,
          "--stage-zoom": (t.stageZoom / 100),
          "--vignette-opacity": t.stageVignette ? 0.18 : 0,
        }}>
          {(() => {
            const showGen = stageTab === "mockup" && activeGallery >= 0 && gallery[activeGallery] && gallery[activeGallery].url;
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

          {t.showFloorTag && <div className="stage-summary-top">
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

          {stageTab === "mockup" && <button className="gen-fab" onClick={handleGenerate} style={{
            left: t.fabAlign === "left" ? 24 : t.fabAlign === "right" ? "auto" : "50%",
            right: t.fabAlign === "right" ? 24 : "auto",
            transform: t.fabAlign === "center" ? "translateX(-50%)" : "none",
          }}>
            <span className="ico">{Ic.sparkle}</span>
            <span>Generuj wariant</span>
            <span className="cost">${cost}</span>
            <span className="kbd">⌘ ↵</span>
          </button>}

          {stageTab === "json" && (
            <div className="stage-json">
              <div className="stage-json-head">
                <button className={"stage-json-copy " + (copied ? "ok" : "")} onClick={() => {
                  const data = {
                    product: { type: st.kind, base: st.uploaded ? "sofa-katalog-2026.jpg" : null },
                    variant: {
                      color: st.color === "custom" ? { custom: st.colorCustom } : { id: colorObj?.id, name: colorObj?.name, hex: colorObj?.hex },
                      material: { id: matObj?.id, name: matObj?.name, notes: st.matNotes || null },
                      size: { id: sizeObj?.id, label: sizeObj?.name, dim: sizeObj?.dim },
                      legs: st.kind === "bed" ? "disabled_for_bed" : st.legs,
                    },
                    scene: {
                      environment: envObj?.id,
                      camera: camObj?.id,
                      lens: st.lens, time_of_day: st.tod, shadows: st.shadow,
                    },
                    references: st.refs.filter(Boolean),
                    output: { model: st.model, aspect: st.aspect, resolution: st.res.split(" ")[0], seed: st.seed || null },
                  };
                  navigator.clipboard?.writeText(JSON.stringify(data, null, 2));
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1400);
                }}>
                  {copied ? <><span>{Ic.check}</span> Skopiowano</> : <><span>{Ic.copy}</span> Kopiuj</>}
                </button>
              </div>
              <pre><code dangerouslySetInnerHTML={{__html: highlightJson(JSON.stringify({
                product: { type: st.kind, base: st.uploaded ? "sofa-katalog-2026.jpg" : null },
                variant: {
                  color: st.color === "custom" ? { custom: st.colorCustom } : { id: colorObj?.id, name: colorObj?.name, hex: colorObj?.hex },
                  material: { id: matObj?.id, name: matObj?.name, notes: st.matNotes || null },
                  size: { id: sizeObj?.id, label: sizeObj?.name, dim: sizeObj?.dim },
                  legs: st.kind === "bed" ? "disabled_for_bed" : st.legs,
                },
                scene: {
                  environment: envObj?.id,
                  camera: camObj?.id,
                  lens: st.lens, time_of_day: st.tod, shadows: st.shadow,
                },
                references: st.refs.filter(Boolean),
                output: { model: st.model, aspect: st.aspect, resolution: st.res.split(" ")[0], seed: st.seed || null },
              }, null, 2))}}/></pre>
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

        {/* 01 — output (was 09) */}
        <Section num="01" title="Wyjście" summary={`${st.model.includes("pro") ? "pro" : "flash"} · ${st.aspect} · ${st.res.split(" ")[0]}`}
          help="Model, proporcje, rozdzielczość. Flash: szybki, do 1K, max 3 referencje. Pro: do 2K, droższy 4×.">
          <div className="out-grid">
            <div>
              <div className="field-lbl">model</div>
              <select className="select" value={st.model} onChange={e => set({ model: e.target.value })}>
                <option value="gemini-2.5-flash-image">gemini-2.5-flash-image</option>
                <option value="gemini-2.5-pro-image">gemini-2.5-pro-image</option>
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
              <select className="select" value={st.res} onChange={e => set({ res: e.target.value })}>
                <option>1K — Flash limit</option>
                <option>2K — tylko Pro</option>
              </select>
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
                  <div className="lead">{st.envFile || "Wgraj zdjęcie tła"}</div>
                  <div className="sub">{st.envFile ? "kliknij aby zmienić" : "model użyje go jako referencji oświetlenia i kolorów"}</div>
                </div>
                <button className="size-pill" onClick={() => set({ envFile: st.envFile ? null : "moje-wnetrze.jpg" })}>
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
        <Section num="08" title="Kamera i światło" summary={camObj?.name + " · " + st.lens.split(" — ")[0]}
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
                <option>35 mm — szeroki kontekst</option>
                <option>50 mm — naturalna</option>
                <option>85 mm — produktowa</option>
              </select>
            </div>
            <div>
              <div className="field-lbl">pora dnia</div>
              <select className="select" value={st.tod} onChange={e => set({ tod: e.target.value })}>
                <option>poranek — chłodne, miękkie</option>
                <option>południe — neutralne</option>
                <option>złota godzina — ciepłe</option>
                <option>wieczór — lampy</option>
              </select>
            </div>
            <div>
              <div className="field-lbl">cienie</div>
              <select className="select" value={st.shadow} onChange={e => set({ shadow: e.target.value })}>
                <option>miękkie rozproszone</option>
                <option>kierunkowe — okno</option>
                <option>twarde — studio</option>
              </select>
            </div>
          </div>
        </Section>

        {/* 08 — references */}
        <Section num="09" title="Referencje" summary={st.refs.filter(Boolean).length + " / 3"}
          help="Maks. 3 obrazy — limit modelu Flash. Wybierz najtrafniejsze kadry, nie cały moodboard.">
          <div className="refs">
            {[0, 1, 2].map(i => (
              <div key={i}
                className={"ref-slot " + (st.refs[i] ? "filled" : "")}
                onClick={() => {
                  const next = [...st.refs];
                  next[i] = next[i] ? null : ["nastrojowa.jpg", "tkanina-zbliz.jpg", "salon-ref.jpg"][i];
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
        </Section>

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
              navigator.clipboard?.writeText(JSON.stringify(st, null, 2));
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
