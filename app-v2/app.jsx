/* global React, ReactDOM, Ic, NS_DATA, Steps */
const { useState, useMemo, useEffect, useCallback } = React;
const { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS, STEPS,
        LENSES, TIMES_OF_DAY, SHADOWS } = NS_DATA;
const { StepPhoto, StepColor, StepMaterial, StepSize, StepLegs, StepScene, StepRefs, Advanced } = Steps;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "stagePadding": 18,
  "showCostBar": true,
  "denseStepper": false,
  "warmth": "warm"
}/*EDITMODE-END*/;

const API_KEY_STORAGE = "nano-sofa-v2-api-key";

function App() {
  const [tab, setTab] = useState("gen"); // gen | compare | costs | schema
  const [active, setActive] = useState("photo");

  // API key — held in localStorage only; never sent anywhere except backend on submit.
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(API_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(API_KEY_STORAGE, apiKey); } catch {}
  }, [apiKey]);
  const [showKeyEdit, setShowKeyEdit] = useState(false);

  // wizard state
  const [st, setSt] = useState({
    uploaded: false, baseFile: null, baseFileName: "", baseFileSize: 0, basePreviewUrl: null,
    alpha: false, kind: "sofa",
    color: "cream", colorCustom: "", colorCustomHex: "",
    mat: "boucle", matNotes: "",
    size: "3",
    legs: "keep",
    cam: "studio", lens: "50mm_natural", tod: "noon_neutral", shadow: "soft_diffuse",
    refs: [null, null, null],
    model: "gemini-3.1-flash-image-preview", aspect: "4:3", res: "1K", seed: "",
  });
  const set = patch => setSt(s => ({...s, ...patch}));

  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [gallery, setGallery] = useState([]); // { url, color, tag, cost }
  const [activeGallery, setActiveGallery] = useState(-1);

  const colorObj = useMemo(() => COLORS.find(c => c.id === st.color), [st.color]);
  const matObj = useMemo(() => MATERIALS.find(m => m.id === st.mat), [st.mat]);
  const sizeObj = useMemo(() => {
    const list = st.kind === "bed" ? SIZES_BED : SIZES_SOFA;
    return list.find(s => s.id === st.size) || list[0];
  }, [st.kind, st.size]);
  const camObj = useMemo(() => CAMERAS.find(c => c.id === st.cam), [st.cam]);
  const lensObj = useMemo(() => LENSES.find(l => l.id === st.lens), [st.lens]);

  // est cost
  const cost = useMemo(() => {
    const base = st.model.includes("pro") ? 0.12 : 0.03;
    const refMult = 1 + st.refs.filter(Boolean).length * 0.15;
    const resMult = st.res.startsWith("2K") ? 1.6 : 1;
    return (base * refMult * resMult).toFixed(4);
  }, [st.model, st.refs, st.res]);

  const handleGenerate = async () => {
    setGenError("");
    if (!apiKey.trim()) {
      setGenError("Wklej klucz Gemini API u góry strony.");
      setShowKeyEdit(true);
      return;
    }
    if (!st.baseFile) {
      setGenError("Wgraj zdjęcie bazowe w kroku 01.");
      setActive("photo");
      return;
    }
    const fd = new FormData();
    fd.append("api_key", apiKey.trim());
    fd.append("kind", st.kind);
    fd.append("color", st.color);
    // Merge free-text + optional HEX into the single color_custom field the
    // server injects verbatim into the prompt (mirrors app-v2.jsx).
    fd.append("color_custom", (() => {
      const txt = (st.colorCustom || "").trim();
      const hex = (st.colorCustomHex || "").trim();
      if (!hex) return txt;
      const hexNote = `exact upholstery colour hex ${hex}`;
      return txt ? `${txt} (${hexNote})` : hexNote;
    })());
    fd.append("mat", st.mat);
    fd.append("mat_notes", st.matNotes || "");
    fd.append("size", st.size);
    fd.append("legs", st.legs);
    fd.append("cam", st.cam);
    fd.append("lens", st.lens);
    fd.append("tod", st.tod);
    fd.append("shadow", st.shadow);
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

  const idx = STEPS.findIndex(s => s.id === active);
  const goNext = () => idx < STEPS.length - 1 && setActive(STEPS[idx+1].id);
  const goPrev = () => idx > 0 && setActive(STEPS[idx-1].id);

  // filled for stepper "done"
  const doneSet = useMemo(() => {
    const out = new Set();
    if (st.uploaded) out.add("photo");
    if (st.color) out.add("color");
    if (st.mat) out.add("mat");
    if (st.size) out.add("size");
    if (st.legs) out.add("legs");
    if (st.cam) out.add("scene");
    if (st.refs.some(Boolean)) out.add("refs");
    return out;
  }, [st]);

  const stepHead = STEPS[idx];

  return (
    <div className="app">
      {/* Topbar */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"></div>
          <div>
            <div className="brand-name">Nano Sofa <span className="light">studio</span></div>
          </div>
          <div className="brand-sub">generator zdjęć produktów</div>
        </div>
        <div className="topbar-tabs">
          {[["gen","Generuj"], ["compare","Porównaj / Wsadowo"], ["costs","Koszty"], ["schema","Schemat / Nogi"]].map(([id,l]) => (
            <button key={id} className={"tt " + (tab===id?"active":"")} onClick={() => setTab(id)}>{l}</button>
          ))}
        </div>
        <div style={{display:"flex", alignItems:"center", gap: 8}}>
          {showKeyEdit ? (
            <div style={{display:"flex", gap:6, alignItems:"center"}}>
              <input
                autoFocus
                type="password"
                className="input"
                placeholder="AIza... (wklej nowy klucz)"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                onFocus={e => e.target.select()}
                onBlur={() => setShowKeyEdit(false)}
                onKeyDown={e => { if (e.key === "Enter" || e.key === "Escape") setShowKeyEdit(false); }}
                style={{width: 250, padding: "8px 12px", fontSize: 12, fontFamily: "Geist Mono"}}
              />
              {apiKey && (
                <button
                  type="button"
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => { setApiKey(""); try { localStorage.removeItem(API_KEY_STORAGE); } catch {} }}
                  title="usuń zapisany klucz, żeby wpisać nowy"
                  style={{padding:"8px 10px", fontSize: 11, fontFamily:"Geist Mono", cursor:"pointer", whiteSpace:"nowrap", borderRadius: 6, border:"1px solid rgba(0,0,0,.15)", background:"#fff"}}
                >wyczyść</button>
              )}
            </div>
          ) : (
            <button className="api-status" onClick={() => setShowKeyEdit(true)} title="kliknij aby wkleić / zmienić klucz">
              <span className={"dot " + (apiKey ? "" : "off")}></span>
              <span>klucz Gemini</span>
              <span className="key-pill">
                {apiKey ? `AIza••••${apiKey.slice(-4)}` : "wklej klucz"}
              </span>
            </button>
          )}
        </div>
      </header>

      {/* Stepper */}
      <aside className="stepper">
        <div className="stepper-title">Kreator wariantu</div>
        {STEPS.map(s => (
          <div key={s.id}
               className={"step " + (active === s.id ? "active" : "") + (doneSet.has(s.id) && active!==s.id ? " done" : "")}
               onClick={() => setActive(s.id)}>
            <div className="step-num">{doneSet.has(s.id) && active!==s.id ? Ic.check : s.num}</div>
            <div className="step-label">
              <div className="top">{s.top}</div>
              <div className="bot">{stepBot(s.id, st, colorObj, matObj, sizeObj, camObj)}</div>
            </div>
            {s.id === "legs" && st.kind === "bed" && (
              <div className="step-tag">n/d</div>
            )}
            {s.id === "refs" && (
              <div className="step-tag">{st.refs.filter(Boolean).length}/3</div>
            )}
          </div>
        ))}

        <div className="stepper-foot">
          <div style={{fontSize: 11, color: "var(--ink-3)", letterSpacing:"0.06em", textTransform:"uppercase"}}>Szybkie presety</div>
          <div className="preset-row">
            <button className="preset-pill" onClick={() => set({color:"cream", mat:"boucle", cam:"studio"})}>katalog ↗</button>
            <button className="preset-pill" onClick={() => set({color:"carmel", mat:"velvet", cam:"lounge"})}>lifestyle ↗</button>
            <button className="preset-pill" onClick={() => set({color:"cream", mat:"linen", cam:"loft"})}>skandyn. ↗</button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        <div className="main-head">
          <div>
            <div className="main-eyebrow">Krok {stepHead.num} z {String(STEPS.length).padStart(2,"0")} · {stepHead.top}</div>
            <h1 className="main-title serif">{TITLES[stepHead.id]}</h1>
            <p className="main-sub">{SUBS[stepHead.id]}</p>
            <div className="summary-strip">
              <div className="summary-chip"><span className="k">typ</span> {st.kind === "bed" ? "łóżko" : "sofa"}</div>
              <div className="summary-chip"><span className="k">kolor</span> {colorObj?.name || "własny"}</div>
              <div className="summary-chip"><span className="k">tkanina</span> {matObj?.name}</div>
              <div className="summary-chip"><span className="k">rozmiar</span> {sizeObj?.name}</div>
              <div className="summary-chip"><span className="k">scena</span> {camObj?.name}</div>
            </div>
          </div>
          <div className="step-pager">
            <button className="pager-btn" onClick={goPrev} disabled={idx===0}>{Ic.arrowL}</button>
            <span style={{fontFamily:"Geist Mono", fontSize: 12}}>{idx+1} / {STEPS.length}</span>
            <button className="pager-btn" onClick={goNext} disabled={idx===STEPS.length-1}>{Ic.arrowR}</button>
          </div>
        </div>

        {active === "photo" && <StepPhoto st={st} set={set} />}
        {active === "color" && <StepColor st={st} set={set} />}
        {active === "mat"   && <StepMaterial st={st} set={set} />}
        {active === "size"  && <StepSize st={st} set={set} />}
        {active === "legs"  && <StepLegs st={st} set={set} />}
        {active === "scene" && <StepScene st={st} set={set} />}
        {active === "refs"  && <StepRefs st={st} set={set} />}

        <Advanced st={st} set={set} />
      </main>

      {/* Preview */}
      <aside className="preview">
        <div className="preview-head">
          <div>
            <div className="preview-title serif">Podgląd renderingu</div>
            <div className="preview-summary">{colorObj?.name} · {matObj?.name} · {sizeObj?.name} · {camObj?.name}</div>
          </div>
          <div className="seg" style={{fontSize: 11}}>
            <button className="on">live</button>
            <button>oryginał</button>
          </div>
        </div>

        <div className="preview-stage">
          {(() => {
            const showGen = activeGallery >= 0 && gallery[activeGallery] && gallery[activeGallery].url;
            const showBase = activeGallery === -1 && st.basePreviewUrl;
            if (showGen) {
              return <img src={gallery[activeGallery].url} alt="rendering"
                          style={{position:"absolute",inset:0,width:"100%",height:"100%",objectFit:"contain",background:"#1a1b19"}} />;
            }
            if (showBase) {
              return <img src={st.basePreviewUrl} alt="baza"
                          style={{position:"absolute",inset:0,width:"100%",height:"100%",objectFit:"contain",background:"#1a1b19"}} />;
            }
            return (
              <div className="stage-sofa" style={{"--mat-color": colorObj?.hex || "#6F8C68"}}>
                <FabricOverlay tex={matObj?.tex} />
                <div className="stage-legs">
                  {Array.from({length: 4}).map((_,i) => <span key={i} />)}
                </div>
              </div>
            );
          })()}
          <div className="preview-pill pp-dim"><span className="ico">{Ic.scale}</span>{sizeObj?.dim}</div>
          <div className="preview-pill pp-mat">{matObj?.name}</div>
          <div className="preview-pill pp-cam"><span className="ico">{Ic.camera}</span>{camObj?.name}</div>
          <div className="preview-pill pp-lens"><span className="ico">{Ic.lens}</span>{lensObj?.name?.split(" — ")[0] || "—"}</div>

          {generating && (
            <div className="gen-overlay">
              <div className="gen-card">
                <div style={{fontSize: 13, display:"flex", alignItems:"center", gap: 8}}>
                  <span style={{color:"var(--accent-soft)"}}>{Ic.sparkle}</span>
                  Renderuję wariant…
                </div>
                <div className="gen-bar"><div></div></div>
                <div style={{fontSize: 11, color:"rgba(255,255,255,.6)", fontFamily:"Geist Mono"}}>
                  {st.model} · {st.aspect} · {st.res.split(" ")[0]} · ~12s
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="preview-gallery">
          <div className={"gallery-item empty " + (activeGallery === -1 ? "active" : "")}
               onClick={() => setActiveGallery(-1)}>baza</div>
          {gallery.map((g, i) => (
            <div key={i}
                 className={"gallery-item " + (i === activeGallery ? "active" : "")}
                 onClick={() => setActiveGallery(i)}>
              {g.url
                ? <img src={g.url} alt={g.tag} style={{position:"absolute",inset:0,width:"100%",height:"100%",objectFit:"cover"}} />
                : <div className="gi-render" style={{background:g.color}}></div>}
              <div className="gi-meta">{g.tag}</div>
            </div>
          ))}
        </div>
      </aside>

      {/* Dock */}
      <footer className="dock">
        <div className="dock-cost">
          <div className="label">Szacunkowy koszt</div>
          <div className="value">${cost}</div>
          <div className="breakdown">{st.model.includes("pro") ? "pro" : "flash"} · {st.refs.filter(Boolean).length} ref · {st.res.split(" ")[0]}</div>
        </div>

        <div className="validation" style={genError ? {borderColor:"var(--danger)", color:"var(--danger)"} : {}}>
          {genError
            ? <><span style={{color:"var(--danger)"}}>!</span>{genError}</>
            : <><span className="ok">{Ic.check}</span>{
                !apiKey ? "Wklej klucz API u góry strony" :
                !st.baseFile ? "Wgraj zdjęcie bazowe (krok 01)" :
                "Wszystkie ograniczenia spełnione"
              }</>}
        </div>

        <div className="dock-spacer"></div>

        <div className="dock-budget">
          <span>Sesja</span>
          <div className="budget-bar"><div className="fill" style={{width: "22%"}}></div></div>
          <span style={{fontFamily:"Geist Mono"}}>$0.89 / $5.00</span>
        </div>

        <button className="btn-secondary">Zapisz preset</button>
        <button className="btn-primary" onClick={handleGenerate}>
          <span>{Ic.sparkle}</span>
          Generuj wariant
          <span className="kbd">⌘ ↵</span>
        </button>
      </footer>
    </div>
  );
}

const TITLES = {
  photo:  "Zacznij od zdjęcia — reszta dopasuje się do tego mebla.",
  color:  "Wybierz kolor tapicerki, jaki ma ujrzeć kamera.",
  mat:    "Tkanina dyktuje światło — wybierz najbliższy materiał.",
  size:   "Konfiguracja zmienia proporcje całej sceny.",
  legs:   "Nogi mebla — domyślnie zachowujemy te z bazy.",
  scene:  "Kamera i światło — w jakim kontekście pokazujemy mebel.",
  refs:   "Dodaj referencje stylu, jeśli chcesz prowadzić model dalej.",
};
const SUBS = {
  photo:  "Wgraj produkt bazowy. Model trzyma się jego sylwetki, my zmieniamy resztę. Im czystsza baza, tym wierniejszy rendering.",
  color:  "Modele rozpoznają nazwy z naszej palety najwierniej. Jeśli potrzebujesz odcienia spoza listy — opisz go słownie.",
  mat:    "Lista zawiera tylko materiały, które Gemini odwzorowuje wiarygodnie. Notatki o teksturze poniżej pomagają w detalu.",
  size:   "Lista dostępnych rozmiarów zmienia się z typem produktu — sofy mają miejsca, łóżka mają wymiary materaca.",
  legs:   "Tu kończy się rola formularza w fizyce mebla. Dla łóżek krok jest pomijany.",
  scene:  "Każda scena to gotowy zestaw: tło, oświetlenie, kąt. Możesz dostroić ogniskową, porę dnia i cienie poniżej.",
  refs:   "Maks. 3 obrazy — to limit modelu Flash. Nie wgrywaj całego moodboardu, wybierz najtrafniejsze kadry.",
};

function stepBot(id, st, c, m, s, cam) {
  if (id === "photo") return st.uploaded ? (st.baseFileName || "wgrane") : "wymagane";
  if (id === "color") return st.color === "custom" ? ("własny" + (st.colorCustomHex ? " · " + st.colorCustomHex : " opis")) : c?.name;
  if (id === "mat")   return m?.name + (st.matNotes ? " · z notatkami" : "");
  if (id === "size")  return s?.name + " · " + s?.dim;
  if (id === "legs")  return st.kind === "bed" ? "wyłączone" : (LEGS.find(l=>l.id===st.legs)?.name || "");
  if (id === "scene") return cam?.name;
  if (id === "refs")  return st.refs.filter(Boolean).length === 0 ? "puste" : st.refs.filter(Boolean).length + " z 3";
  return "";
}

function FabricOverlay({tex}) {
  if (!tex) return null;
  // pseudo overlay via CSS — handled in stylesheet
  return <div className="preview-fabric-overlay" data-tex={tex} />;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
