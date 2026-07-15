/* global React, Ic, NS_DATA */
const { useState, useMemo, useEffect } = React;
const { COLORS, MATERIALS, SIZES_SOFA, SIZES_BED, CAMERAS, LEGS, STEPS,
        LENSES, TIMES_OF_DAY, SHADOWS } = NS_DATA;

/* ====== Step 1 — Photo & type ====== */
function StepPhoto({ st, set }) {
  const has = !!st.baseFile;
  const fileRef = React.useRef(null);

  const onPick = (file) => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    set({
      baseFile: file,
      baseFileName: file.name,
      baseFileSize: file.size,
      basePreviewUrl: url,
      uploaded: true,
    });
  };

  const fmtSize = (b) => b < 1024*1024 ? (b/1024).toFixed(0) + " KB" : (b/1024/1024).toFixed(1) + " MB";

  return (
    <div className="card">
      <div className="row" style={{gridTemplateColumns: "1.4fr 1fr", gap: 22}}>
        <div>
          <div className="field-label">Zdjęcie produktu bazowego</div>
          <div className="field-help">Przeciągnij plik z pulpitu albo kliknij. JPG, PNG, max 12 MB. To Twój punkt startowy — model trzyma się jego kształtu.</div>
          <input ref={fileRef} type="file" accept="image/*" style={{display:"none"}}
                 onChange={e => onPick(e.target.files && e.target.files[0])} />
          <div
            className={"dropzone " + (has ? "has-image" : "")}
            onClick={() => fileRef.current && fileRef.current.click()}
            onDragOver={e => e.preventDefault()}
            onDrop={e => { e.preventDefault(); onPick(e.dataTransfer.files && e.dataTransfer.files[0]); }}
          >
            <div className="dropzone-thumb">
              {has && st.basePreviewUrl
                ? <img src={st.basePreviewUrl} alt="" style={{width:"100%",height:"100%",objectFit:"cover"}} />
                : Ic.upload}
            </div>
            <div className="dropzone-body">
              <div className="lead">{has ? st.baseFileName : "Upuść zdjęcie tutaj"}</div>
              <div className="help">{has ? fmtSize(st.baseFileSize) + " · gotowe do generowania" : "lub kliknij, aby wybrać z dysku"}</div>
              <div className="dz-meta">
                {has ? (
                  <>
                    <span className="dz-tag">{(st.baseFile.type || "image").replace("image/","")}</span>
                    <span className="dz-tag" style={{color: "var(--accent-ink)", background: "var(--accent-soft)"}}>wgrane</span>
                  </>
                ) : (
                  <>
                    <span className="dz-tag">JPG / PNG / WEBP</span>
                    <span className="dz-tag">≥ 1024 px</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <label className="check" style={{marginTop: 14}}>
            <input type="checkbox" checked={st.alpha} onChange={e => set({alpha: e.target.checked})} />
            <span className="box"></span>
            Zdjęcie ma kanał alfa — spłaszcz do 18% szarości tła
          </label>
        </div>

        <div>
          <div className="field-label">Co generujemy?</div>
          <div className="field-help">To zmienia słownictwo promptu i listę rozmiarów. Wybierz „łóżko” aby wyłączyć dorabianie nóg.</div>
          <div className="type-grid">
            <div className={"type-card " + (st.kind === "sofa" ? "sel" : "")} onClick={() => set({kind: "sofa"})}>
              <div className="type-icon">{Ic.sofa}</div>
              <div>
                <div className="type-name">sofa / fotel</div>
                <div className="type-desc">tapicerka, nogi, podłokietniki</div>
              </div>
            </div>
            <div className={"type-card " + (st.kind === "bed" ? "sel" : "")} onClick={() => set({kind: "bed"})}>
              <div className="type-icon">{Ic.bed}</div>
              <div>
                <div className="type-name">łóżko</div>
                <div className="type-desc">rama, materac, zagłówek</div>
              </div>
            </div>
          </div>

          <div className="ai-tip">
            <span className="ico">{Ic.sparkle}</span>
            <div>Dobre zdjęcie bazowe = neutralne tło, równe światło, frontalna lub 3/4 perspektywa. Cienie pod meblem są w porządku.</div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ====== Step 2 — Color ====== */
function StepColor({ st, set }) {
  return (
    <div className="card">
      <div className="field-label">Kolor tapicerki</div>
      <div className="field-help">Wybierz preset z palety albo zdefiniuj własny — opisem słownym, dokładnym HEX-em lub oboma naraz. Modele rozpoznają nazwy z naszej palety najwierniej.</div>
      <div className="swatch-row">
        {COLORS.map(c => (
          <div key={c.id}
               className={"swatch " + (st.color === c.id ? "sel" : "")}
               onClick={() => set({color: c.id})}>
            <div className="swatch-fill fabric" style={{background: c.hex}}></div>
            <div className="swatch-name">{c.name}</div>
            <div className="swatch-hex">{c.hex}</div>
          </div>
        ))}
        <div className={"swatch custom " + (st.color === "custom" ? "sel" : "")}
             onClick={() => set({color: "custom"})}>
          <div className="swatch-fill" style={st.colorCustomHex ? {background: st.colorCustomHex} : undefined}>{st.colorCustomHex ? "" : "+"}</div>
          <div className="swatch-name">własny</div>
          <div className="swatch-hex">{st.colorCustomHex || "opis / HEX"}</div>
        </div>
      </div>

      {st.color === "custom" && (
        <div style={{marginTop: 14}}>
          <textarea className="input"
            placeholder="np. ciepła szałwia z szarym podtonem, lekko stonowana, jak na zdjęciu salonu Norrgavel z 2024"
            value={st.colorCustom}
            onChange={e => set({colorCustom: e.target.value})} />
          <div style={{display: "flex", alignItems: "center", gap: 10, marginTop: 8}}>
            <input type="color"
              value={st.colorCustomHex || "#EFEFEE"}
              onChange={e => set({colorCustomHex: e.target.value.toUpperCase()})}
              style={{width: 42, height: 32, padding: 0, border: "1px solid var(--line, #ccc)", borderRadius: 6, background: "none", cursor: "pointer"}} />
            <input type="text" className="input" style={{width: 130, fontFamily: "Geist Mono, monospace"}}
              placeholder="#RRGGBB (opcja)"
              value={st.colorCustomHex}
              onChange={e => {
                const v = e.target.value.trim().toUpperCase();
                if (v === "" || /^#?[0-9A-F]{0,6}$/.test(v)) set({colorCustomHex: v && !v.startsWith("#") ? "#" + v : v});
              }} />
            {st.colorCustomHex && (
              <button type="button"
                style={{fontSize: 11, padding: "4px 10px", border: "1px solid var(--line, #ccc)", borderRadius: 6, background: "transparent", cursor: "pointer", color: "var(--ink-3, #888)"}}
                onClick={() => set({colorCustomHex: ""})}>wyczyść HEX</button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ====== Step 3 — Material ====== */
function StepMaterial({ st, set }) {
  return (
    <div className="card">
      <div className="field-label">Materiał / tkanina</div>
      <div className="field-help">Zamknięta lista — to materiały, które model odwzorowuje najwierniej. Notatki o teksturze (poniżej) doprecyzowują finish.</div>
      <div className="mat-row">
        {MATERIALS.map(m => (
          <div key={m.id}
               className={"mat-card " + (st.mat === m.id ? "sel" : "")}
               onClick={() => set({mat: m.id})}>
            <div className={"mat-tex " + m.tex}></div>
            <div className="mat-meta">
              <div className="mat-name">{m.name}</div>
              <div className="mat-prop">{m.prop}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{marginTop: 16}}>
        <div className="field-label" style={{marginBottom: 4}}>Notatki o teksturze <span style={{color: "var(--ink-3)", fontWeight: 400}}>(opcjonalne)</span></div>
        <div className="field-help">Dla bouclé: gęstość pętelek. Dla aksamitu: kierunek włosa względem kamery.</div>
        <textarea className="input"
          placeholder="np. gęste pętelki bouclé, dłuższy włos przy oparciu, lekka mechatość"
          value={st.matNotes}
          onChange={e => set({matNotes: e.target.value})} />
      </div>
    </div>
  );
}

/* ====== Step 4 — Size ====== */
function StepSize({ st, set }) {
  const sizes = st.kind === "bed" ? SIZES_BED : SIZES_SOFA;
  return (
    <div className="card">
      <div className="field-label">{st.kind === "bed" ? "Rozmiar materaca" : "Liczba miejsc"}</div>
      <div className="field-help">Lista zmienia się z typem produktu. Schemat poniżej pomaga ocenić proporcje.</div>
      <div className="size-row">
        {sizes.map(s => (
          <div key={s.id}
               className={"size-card " + (st.size === s.id ? "sel" : "")}
               onClick={() => set({size: s.id})}>
            <div className="size-diagram">
              <div className="seat">
                {Array.from({length: s.cushions}).map((_, i) => <div key={i} className="cushion" />)}
              </div>
            </div>
            <div className="size-name">{s.name}</div>
            <div className="size-dim">{s.dim}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ====== Step 5 — Legs ====== */
function StepLegs({ st, set }) {
  const disabled = st.kind === "bed";
  return (
    <div className="card">
      <div className="field-label">Nogi mebla</div>
      <div className="field-help">
        {disabled
          ? "Wybrałeś łóżko — dorabianie nóg jest wyłączone, formularz zachowa cokół z bazy."
          : "Domyślnie zachowujemy nogi z bazowego zdjęcia. Wybierz inne tylko jeśli celowo chcesz je zmienić."}
      </div>
      <div className="leg-row" style={{opacity: disabled ? 0.45 : 1, pointerEvents: disabled ? "none" : "auto"}}>
        {LEGS.map(l => (
          <div key={l.id}
               className={"leg-card " + (st.legs === l.id ? "sel" : "")}
               onClick={() => set({legs: l.id})}>
            <div className="leg-svg">
              <LegSvg id={l.id} />
            </div>
            <div className="leg-name">{l.name}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LegSvg({id}) {
  const stroke = "#3A3B37";
  if (id === "keep") return <svg width="44" height="40" viewBox="0 0 44 40"><rect x="6" y="8" width="32" height="14" rx="3" fill="#E2DDD0"/><text x="22" y="34" fontSize="10" textAnchor="middle" fill={stroke} fontFamily="Geist Mono">obecne</text></svg>;
  if (id === "wood") return <svg width="44" height="40" viewBox="0 0 44 40"><rect x="6" y="8" width="32" height="14" rx="3" fill="#3A3B37"/><path d="M12 22 L10 36 M32 22 L34 36" stroke="#9B7048" strokeWidth="2.5" strokeLinecap="round"/></svg>;
  if (id === "metal") return <svg width="44" height="40" viewBox="0 0 44 40"><rect x="6" y="8" width="32" height="14" rx="3" fill="#3A3B37"/><path d="M12 22 L9 36 M32 22 L35 36" stroke="#7A7770" strokeWidth="1.6" strokeLinecap="round"/></svg>;
  if (id === "block") return <svg width="44" height="40" viewBox="0 0 44 40"><rect x="6" y="8" width="32" height="14" rx="3" fill="#3A3B37"/><rect x="9" y="22" width="6" height="12" fill="#9B7048"/><rect x="29" y="22" width="6" height="12" fill="#9B7048"/></svg>;
  if (id === "hidden") return <svg width="44" height="40" viewBox="0 0 44 40"><rect x="6" y="8" width="32" height="18" rx="3" fill="#3A3B37"/><rect x="8" y="26" width="28" height="6" fill="#1A1B19"/></svg>;
  if (id === "swivel") return <svg width="44" height="40" viewBox="0 0 44 40"><rect x="6" y="8" width="32" height="12" rx="3" fill="#3A3B37"/><path d="M22 20 L22 30" stroke="#7A7770" strokeWidth="2"/><ellipse cx="22" cy="33" rx="10" ry="3" fill="#7A7770"/></svg>;
  return null;
}

/* ====== Step 6 — Camera & lighting ====== */
function StepScene({ st, set }) {
  return (
    <div className="card">
      <div className="field-label">Kamera i światło</div>
      <div className="field-help">Wybór sceny ustawia tło, oświetlenie i ogniskową. Możesz później dostroić w „Zaawansowanych”.</div>
      <div className="cam-row">
        {CAMERAS.map(c => (
          <div key={c.id}
               className={"cam-card " + (st.cam === c.id ? "sel" : "")}
               onClick={() => set({cam: c.id})}>
            <div className={"cam-render " + (c.style || "")}>
              <div className="hfloor"></div>
              <div className="hsofa"></div>
            </div>
            <div className="cam-meta">
              <div className="cam-name">{c.name}</div>
              <div className="cam-prop">{c.prop}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="row three" style={{marginTop: 18}}>
        <div>
          <div className="field-label">Ogniskowa</div>
          <select className="select" value={st.lens} onChange={e => set({lens: e.target.value})}>
            {LENSES.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>
        <div>
          <div className="field-label">Pora dnia</div>
          <select className="select" value={st.tod} onChange={e => set({tod: e.target.value})}>
            {TIMES_OF_DAY.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
        <div>
          <div className="field-label">Cienie</div>
          <select className="select" value={st.shadow} onChange={e => set({shadow: e.target.value})}>
            {SHADOWS.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}

/* ====== Step 7 — Refs ====== */
function StepRefs({ st, set }) {
  return (
    <div className="card">
      <div className="field-label">Dodatkowe referencje <span style={{color:"var(--ink-3)", fontWeight: 400}}>(do 3 obrazów)</span></div>
      <div className="field-help">Wgraj zdjęcia, które mają wpłynąć na styl, oświetlenie albo aranżację. Limit modelu: 3 referencje.</div>
      <div className="refs-row">
        {[0,1,2].map(i => (
          <div key={i}
               className={"ref-slot " + (st.refs[i] ? "filled" : "")}
               onClick={() => {
                 const next = [...st.refs];
                 next[i] = next[i] ? null : ["nastrojowa.jpg", "tkanina-zbliz.jpg", "salon-ref.jpg"][i];
                 set({refs: next});
               }}>
            {st.refs[i] ? (
              <div style={{textAlign:"center"}}>
                <div style={{fontFamily:"Geist Mono", fontSize: 11, color: "var(--ink)"}}>{st.refs[i]}</div>
                <div style={{fontSize: 10, color:"var(--ink-3)", marginTop: 4}}>kliknij aby usunąć</div>
              </div>
            ) : (
              <div>
                <div style={{fontSize: 18, marginBottom: 4}}>+</div>
                <div>slot {i+1}</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ====== Advanced (collapsible) ====== */
function Advanced({ st, set }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={"advanced " + (open ? "open" : "")}>
      <div className="head" onClick={() => setOpen(!open)}>
        <div style={{display: "flex", alignItems: "center", gap: 10}}>
          <span style={{color: "var(--ink-3)"}}>{Ic.scale}</span>
          <span>Zaawansowane — model, proporcje, rozdzielczość</span>
          <span style={{fontFamily: "Geist Mono", fontSize: 11, color: "var(--ink-4)"}}>
            {st.model} · {st.aspect} · {st.res}
          </span>
        </div>
        <span className="caret">{Ic.caret}</span>
      </div>
      {open && (
        <div className="body">
          <div>
            <div className="field-label">Model Gemini</div>
            <select className="select" value={st.model} onChange={e => set({model: e.target.value})}>
              <option value="gemini-2.5-flash-image">gemini-2.5-flash-image</option>
              <option value="gemini-2.5-pro-image">gemini-2.5-pro-image</option>
            </select>
            <div className="field-help" style={{marginTop: 6}}>Flash: szybki, do 1K, max 3 referencje. Pro: do 2K, droższy 4×.</div>
          </div>
          <div>
            <div className="field-label">Proporcje</div>
            <select className="select" value={st.aspect} onChange={e => set({aspect: e.target.value})}>
              <option>4:3</option><option>3:2</option><option>1:1</option><option>16:9</option>
            </select>
          </div>
          <div>
            <div className="field-label">Rozdzielczość</div>
            <select className="select" value={st.res} onChange={e => set({res: e.target.value})}>
              <option>1K — Flash limit</option>
              <option>2K — tylko Pro</option>
            </select>
          </div>
          <div>
            <div className="field-label">Seed</div>
            <input className="input" placeholder="puste = losowy" value={st.seed} onChange={e => set({seed: e.target.value})} />
          </div>
        </div>
      )}
    </div>
  );
}

window.Steps = { StepPhoto, StepColor, StepMaterial, StepSize, StepLegs, StepScene, StepRefs, Advanced };
