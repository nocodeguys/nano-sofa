/*
  Nano Sofa — Meli (Lab). Wood-colour recolor of solid-wood beds: upload a
  photo, pick a Meli finish (or describe your own), pick any OpenRouter image
  model — the bed comes back with ONLY its wood recoloured. No upholstery, no
  scene, no camera controls on purpose. Palette + finish photographs come from
  /api/meli/config (app-v2/meli/palette.json + references/), so new colours
  need no frontend change. The OpenRouter key is shared with /editorial and /lab.
*/
import React, { useState, useEffect, useRef, useMemo } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/300.css";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "./styles-v2.css";
import "./editorial.css";
import { NanoTopbar, PageIntro } from "./header.jsx";

const OR_KEY_STORAGE = "nano-sofa-v2-openrouter-key"; // shared with /editorial and /lab
const MAX_CUSTOM_REFS = 4;
const FINISHES = [
  { id: "stain", name: "bejca / olej", hint: "słoje w pełni widoczne, zmienia się tylko odcień" },
  { id: "opaque", name: "kryjący", hint: "farba / lakier kryjący, słoje tylko jako delikatna faktura" },
];

const Ic = {
  sparkle: <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" fill="currentColor"/></svg>,
  upload: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg>,
};

// "Aria 160", "Dąb miodowy" → "aria-160", "dab-miodowy"
function fileSlug(...parts) {
  return parts.filter(Boolean).join("-").toLowerCase().replace(/ł/g, "l")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function App() {
  // ---- OpenRouter key (Meli runs on OpenRouter only) ------------------------
  const [orKey, setOrKey] = useState(() => {
    try { return localStorage.getItem(OR_KEY_STORAGE) || ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem(OR_KEY_STORAGE, orKey); } catch {}
  }, [orKey]);
  const [showKeyEdit, setShowKeyEdit] = useState(() => !orKey);

  // ---- palette + models -----------------------------------------------------
  const [palette, setPalette] = useState([]);
  const [models, setModels] = useState([]);
  const [modelId, setModelId] = useState("");
  const [configError, setConfigError] = useState(false);
  useEffect(() => {
    fetch("/api/meli/config").then(r => r.ok ? r.json() : Promise.reject()).then(c => {
      setPalette(c.palette || []);
      setModels(c.models || []);
      setModelId(c.default_model || (c.models && c.models[0] && c.models[0].id) || "");
    }).catch(() => setConfigError(true));
  }, []);
  const model = models.find(m => m.id === modelId) || null;
  const groups = useMemo(() => {
    const out = [];
    for (const c of palette) {
      const key = c.group || "";
      let g = out.find(x => x.key === key);
      if (!g) { g = { key, colors: [] }; out.push(g); }
      g.colors.push(c);
    }
    return out;
  }, [palette]);

  // ---- form state -----------------------------------------------------------
  const [base, setBase] = useState(null);          // {file, url, w, h}
  const fileRef = useRef(null);
  const [product, setProduct] = useState("");
  const [colorId, setColorId] = useState("");      // "" = own colour
  const [customName, setCustomName] = useState("");
  const [customHex, setCustomHex] = useState("");
  const [customFinish, setCustomFinish] = useState("stain");
  const [customRefs, setCustomRefs] = useState([]); // [{file, url}]
  const refInputRef = useRef(null);
  const [res, setRes] = useState("2K");
  const [quality, setQuality] = useState("");

  useEffect(() => {
    if (!model) return;
    const resolutions = model.resolutions || ["auto"];
    if (!resolutions.includes(res)) setRes(resolutions.includes("2K") ? "2K" : resolutions[0]);
    const qualities = model.qualities || [];
    setQuality(qualities.includes(quality) ? quality : (model.default_quality || ""));
    // eslint-disable-next-line
  }, [modelId]);

  const selected = palette.find(c => c.id === colorId) || null;
  const isCustom = !selected;
  const colorLabel = selected ? selected.name_pl : (customName.trim() || customHex.trim() || "");

  const onPickBase = (f) => {
    if (!f) return;
    const url = URL.createObjectURL(f);
    const img = new Image();
    img.onload = () => setBase({ file: f, url, w: img.naturalWidth, h: img.naturalHeight });
    img.src = url;
  };
  const addCustomRefs = (files) => {
    const next = [...customRefs];
    for (const f of files || []) {
      if (next.length >= MAX_CUSTOM_REFS) break;
      next.push({ file: f, url: URL.createObjectURL(f) });
    }
    setCustomRefs(next);
  };

  // ---- generation -----------------------------------------------------------
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);
  const [shown, setShown] = useState(null);
  const [showBefore, setShowBefore] = useState(false);
  const [history, setHistory] = useState([]);

  const handleGenerate = async () => {
    setError(null);
    if (!orKey.trim()) { setError({ message: "Wklej klucz OpenRouter (sk-or-…) w sekcji Model.", code: "MISSING_OPENROUTER_KEY" }); return; }
    if (!base) { setError({ message: "Wgraj zdjęcie łóżka (sekcja 01).", code: "MISSING_BASE_IMAGE" }); return; }
    if (isCustom && !customName.trim() && !/^#?[0-9a-fA-F]{6}$/.test(customHex.trim())) {
      setError({ message: "Wybierz kolor z palety albo opisz własny (nazwa lub HEX).", code: "MISSING_COLOR" }); return;
    }
    if (busy) return;
    setBusy(true);
    setElapsed(0);
    const t0 = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 250);
    try {
      const fd = new FormData();
      fd.append("openrouter_key", orKey.trim());
      fd.append("model", modelId);
      fd.append("base", base.file);
      fd.append("product_name", product.trim());
      if (selected) {
        fd.append("color", selected.id);
      } else {
        fd.append("custom_name", customName.trim());
        fd.append("custom_hex", customHex.trim());
        fd.append("custom_finish", customFinish);
        for (const r of customRefs) fd.append("references", r.file);
      }
      fd.append("res", res);
      if (quality) fd.append("quality", quality);
      const r = await fetch("/api/meli/recolor", { method: "POST", body: fd });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data || !data.success) {
        setError({
          message: (data && data.error) || "Nie udało się zmienić koloru drewna.",
          code: data && data.error_code,
          detail: data && data.error_detail,
        });
      } else {
        const entry = { ...data, product: product.trim(), before: base.url, at: Date.now() };
        setShown(entry);
        setShowBefore(false);
        setHistory(h => [entry, ...h].slice(0, 16));
      }
    } catch (e) {
      setError({ message: "Błąd sieci lub przekroczono czas oczekiwania. Spróbuj ponownie.", code: "NETWORK_TIMEOUT" });
    } finally {
      clearInterval(timer);
      setBusy(false);
    }
  };

  const mm = String(Math.floor(elapsed / 60));
  const ss = String(elapsed % 60).padStart(2, "0");
  const frameRatio = base ? `${base.w} / ${base.h}` : "4 / 3";
  const vertical = base ? base.h > base.w : false;
  const stageImg = shown && !showBefore ? shown.image_url : (shown ? shown.before : base && base.url);
  const dlName = shown ? `meli-${fileSlug(shown.product, shown.color) || "lozko"}.${shown.format || "jpg"}` : "";

  return (
    <div className="app-frame">
      <NanoTopbar active="meli" hideApiKey adminLabel="klucz OpenRouter w sekcji Model" />
      <div className="shell">
      {/* ================= LEFT — stage ================= */}
      <section className="stage-pane">
        <div className="stage-canvas" style={{ display: "grid", placeItems: "center", padding: "36px 24px 28px", background: "var(--bg-2)" }}>
          <div style={{ width: "100%", display: "grid", justifyItems: "center" }}>
            <div className="ed-frame" style={{ aspectRatio: frameRatio, width: vertical ? "min(72%, 420px)" : "min(92%, 720px)" }}>
              {busy ? (
                <div className="ed-placeholder">
                  <div className="ed-spinner"></div>
                  Zmieniam kolor drewna… {mm}:{ss}<br />
                  <span style={{ opacity: .6 }}>{modelId} · {colorLabel}</span>
                </div>
              ) : stageImg ? (
                <img src={stageImg} alt={shown && !showBefore ? "po zmianie koloru" : "zdjęcie źródłowe"} />
              ) : (
                <div className="ed-placeholder">
                  Tu pojawi się łóżko w nowym kolorze drewna.<br />
                  <span style={{ opacity: .6 }}>Wgraj zdjęcie po prawej, wybierz kolor i naciśnij „Zmień kolor drewna”.</span>
                </div>
              )}
            </div>

            {shown && !busy && (
              <div className="ed-meta">
                <div className="seg">
                  <button className={showBefore ? "" : "on"} onClick={() => setShowBefore(false)}>po</button>
                  <button className={showBefore ? "on" : ""} onClick={() => setShowBefore(true)}>przed</button>
                </div>
                <a className="ed-dl" href={shown.image_url} download={dlName}>⭳ Pobierz {String(shown.format || "jpg").toUpperCase()}</a>
                <span>{shown.color} · {shown.finish === "opaque" ? "kryjący" : "bejca"}</span><span>·</span>
                <span>{shown.model}</span><span>·</span>
                <span>{shown.resolution}{shown.quality ? ` · ${shown.quality}` : ""} · {shown.aspect}</span><span>·</span>
                <span>≈ ${Number(shown.cost || 0).toFixed(3)}</span><span>·</span>
                <span>{Math.round((shown.elapsed_ms || 0) / 100) / 10}s</span>
              </div>
            )}

            {history.length > 1 && (
              <div className="ed-hist">
                {history.map(h => (
                  <img key={h.generation_id} src={h.image_url} alt={h.color} title={`${h.color} · ${h.model}`}
                    className={shown && shown.generation_id === h.generation_id ? "on" : ""}
                    onClick={() => { setShown(h); setShowBefore(false); }} />
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ================= RIGHT — form ================= */}
      <section className="form-pane">
        <PageIntro eyebrow={<>Lab · Meli · <a href="/">← wróć do zdjęć</a></>}>
          Zmiana koloru drewna na zdjęciu łóżka z litego drewna. Zmienia się wyłącznie drewno łóżka —
          kadr, światło, tło, pościel i wszystkie detale zostają jak na zdjęciu źródłowym.
        </PageIntro>

        {configError && (
          <div className="ed-err"><strong>CONFIG</strong> — nie udało się pobrać palety Meli z serwera.</div>
        )}
        {error && (
          <div className="ed-err">
            <strong>{error.code || "Błąd"}</strong> — {error.message}
            {error.detail && (
              <div style={{ marginTop: 6, fontFamily: "'Geist Mono', monospace", fontSize: 11, opacity: .8, wordBreak: "break-word" }}>
                Szczegóły od OpenRouter: {error.detail}
              </div>
            )}
          </div>
        )}

        {/* 01 — photo */}
        <div className="section">
          <div className="sec-head">
            <div className="num">01</div>
            <div className="title serif">Zdjęcie łóżka</div>
            <div className="summary">{base ? `${base.w}×${base.h}` : "wymagane"}</div>
          </div>
          <p className="sec-help">Zdjęcie, na którym zmieni się tylko kolor drewna. Proporcje wyniku dobieramy do zdjęcia.</p>
          <div className="sec-body">
            <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }}
              onChange={e => { onPickBase(e.target.files && e.target.files[0]); e.target.value = ""; }} />
            <div className={"up-row " + (base ? "has" : "")}
              onClick={() => fileRef.current && fileRef.current.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); onPickBase(e.dataTransfer.files && e.dataTransfer.files[0]); }}>
              <div className="up-thumb">
                {base ? <img src={base.url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : Ic.upload}
              </div>
              <div className="up-body">
                <div className="lead">{base ? base.file.name : "Upuść zdjęcie łóżka tutaj"}</div>
                <div className="help">{base ? "kliknij, żeby podmienić" : "lub kliknij · JPG / PNG / WEBP"}</div>
              </div>
            </div>

            <div className="field-lbl" style={{ marginTop: 14 }}>model produktu</div>
            <input className="input" placeholder="np. Meli 160" value={product} maxLength={80}
              onChange={e => setProduct(e.target.value)} />
            <div className="hint">zapisywany w metadanych i nazwie pobranego pliku — nie wpływa na prompt</div>
          </div>
        </div>

        {/* 02 — wood colour */}
        <div className="section">
          <div className="sec-head">
            <div className="num">02</div>
            <div className="title serif">Kolor drewna</div>
            <div className="summary">{colorLabel || "wybierz"}</div>
          </div>
          <p className="sec-help">Kolory Meli mają przypisane zdjęcia próbek — trafiają do modelu jako referencja barwy i wykończenia.</p>
          <div className="sec-body">
            {palette.length === 0 && !configError && (
              <div className="hint" style={{ marginTop: 0, marginBottom: 10 }}>
                paleta Meli jest jeszcze pusta — użyj własnego koloru poniżej
              </div>
            )}
            {groups.map(g => (
              <div key={g.key || "_"} style={{ marginBottom: 10 }}>
                {g.key && <div className="field-lbl" style={{ fontSize: 10, opacity: .8 }}>{g.key}</div>}
                <div className="meli-sw">
                  {g.colors.map(c => (
                    <button key={c.id} className={colorId === c.id ? "on" : ""} onClick={() => setColorId(c.id)}
                      title={`${c.name_pl} · ${c.finish === "opaque" ? "kryjący" : "bejca"}${c.references.length ? ` · ${c.references.length} zdj.` : ""}`}>
                      <span className="chip" style={c.references.length
                        ? { backgroundImage: `url(${c.references[0]})` }
                        : { background: c.hex || "#c9b79c" }} />
                      <span className="nm">{c.name_pl}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}

            <button className={"meli-own " + (isCustom ? "on" : "")} onClick={() => setColorId("")}>
              własny kolor
            </button>
            {isCustom && (
              <div style={{ marginTop: 10 }}>
                <div className="field-lbl">nazwa / opis koloru</div>
                <input className="input" placeholder="np. ciepły orzech z miodowym podtonem"
                  value={customName} onChange={e => setCustomName(e.target.value)} />
                <div className="field-lbl" style={{ marginTop: 12 }}>HEX (opcjonalnie)</div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(customHex) ? customHex : "#a67b5b"}
                    onChange={e => setCustomHex(e.target.value.toUpperCase())}
                    style={{ width: 38, height: 34, padding: 0, border: "1px solid var(--line-2)", borderRadius: 8, background: "none" }} />
                  <input className="input" placeholder="#A67B5B" value={customHex} maxLength={7}
                    onChange={e => setCustomHex(e.target.value)} style={{ maxWidth: 140, fontFamily: "Geist Mono" }} />
                  {customHex && <button className="meli-own" onClick={() => setCustomHex("")}>wyczyść</button>}
                </div>
                <div className="field-lbl" style={{ marginTop: 12 }}>wykończenie</div>
                <div className="seg">
                  {FINISHES.map(f => (
                    <button key={f.id} className={customFinish === f.id ? "on" : ""} onClick={() => setCustomFinish(f.id)}>{f.name}</button>
                  ))}
                </div>
                <div className="hint">{FINISHES.find(f => f.id === customFinish).hint}</div>
                <div className="field-lbl" style={{ marginTop: 12 }}>zdjęcia próbki (opcjonalnie, do {MAX_CUSTOM_REFS})</div>
                <div className="ed-refs">
                  {customRefs.map((r, i) => (
                    <div key={r.url} className="slot">
                      <img src={r.url} alt={`próbka ${i + 1}`} />
                      <button type="button" className="x" onClick={() => setCustomRefs(customRefs.filter((_, j) => j !== i))}>×</button>
                    </div>
                  ))}
                  {customRefs.length < MAX_CUSTOM_REFS && (
                    <div className="slot" onClick={() => refInputRef.current && refInputRef.current.click()}>＋</div>
                  )}
                </div>
                <input ref={refInputRef} type="file" accept="image/*" multiple style={{ display: "none" }}
                  onChange={e => { addCustomRefs(e.target.files); e.target.value = ""; }} />
              </div>
            )}
            {selected && (
              <div className="hint">
                {selected.finish === "opaque" ? "kryjący" : "bejca / olej"}
                {selected.hex ? ` · ${selected.hex}` : ""}
                {` · ${selected.references.length ? selected.references.length + " zdj. próbki" : "bez zdjęcia próbki"}`}
              </div>
            )}
          </div>
        </div>

        {/* 03 — model */}
        <div className="section">
          <div className="sec-head">
            <div className="num">03</div>
            <div className="title serif">Model</div>
            <div className="summary">{res}{quality ? ` · ${quality}` : ""}</div>
          </div>
          <p className="sec-help">Wszystkie modele obrazowe z OpenRouter. Najwierniej edytują zdjęcie Nano Banana i GPT Image; FLUX / Seedream / Krea potrafią przerysować łóżko.</p>
          <div className="sec-body">
            <select className="select" value={modelId} onChange={e => setModelId(e.target.value)}>
              {models.map(m => (
                <option key={m.id} value={m.id}>{m.label}{m.price_hint ? ` · ${m.price_hint}` : ""}</option>
              ))}
            </select>
            {model && model.max_refs < 2 && (
              <div className="hint">ten model przyjmuje tylko zdjęcie łóżka — zdjęcia próbek nie zostaną wysłane</div>
            )}

            {model && (model.qualities || []).length > 0 && (
              <>
                <div className="field-lbl" style={{ marginTop: 14 }}>jakość</div>
                <div className="seg">
                  {model.qualities.map(q => (
                    <button key={q} className={quality === q ? "on" : ""} onClick={() => setQuality(q)}>{q}</button>
                  ))}
                </div>
              </>
            )}
            {model && (model.resolutions || []).length > 0 && model.resolutions[0] !== "auto" && (
              <>
                <div className="field-lbl" style={{ marginTop: 14 }}>rozdzielczość</div>
                <div className="seg">
                  {model.resolutions.map(r => (
                    <button key={r} className={res === r ? "on" : ""} onClick={() => setRes(r)}>{r}</button>
                  ))}
                </div>
              </>
            )}

            <div className="field-lbl" style={{ marginTop: 14 }}>klucz OpenRouter</div>
            {showKeyEdit || !orKey ? (
              <input type="password" className="input" placeholder="sk-or-…" value={orKey}
                onChange={e => setOrKey(e.target.value)} onBlur={() => orKey && setShowKeyEdit(false)}
                style={{ fontFamily: "Geist Mono", fontSize: 13 }} />
            ) : (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span className="mono" style={{ fontSize: 12 }}>sk-or-…{orKey.slice(-4)}</span>
                <button className="meli-own" onClick={() => setShowKeyEdit(true)}>zmień</button>
              </div>
            )}
            <div className="hint">
              trzymany tylko w tej przeglądarce, ten sam co w Editorial i Lab · pobierz z{" "}
              <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">openrouter.ai/settings/keys</a>
            </div>
          </div>
        </div>

        {/* foot */}
        <div className="form-foot">
          <div className="foot-summary">
            <div className="foot-lead">{busy ? `Zmieniam kolor… ${mm}:${ss}` : "Gotowe do generowania"}</div>
            <div className="foot-meta">
              <span className="mono">{modelId}</span><span className="dot">·</span>
              <span className="mono">{colorLabel || "brak koloru"}</span>
            </div>
          </div>
          <div className="foot-actions">
            <button className="foot-gen" onClick={handleGenerate} disabled={busy}
              style={busy ? { opacity: .6, cursor: "wait" } : {}}>
              <span className="ico">{Ic.sparkle}</span>
              <span>{busy ? "Generuję…" : "Zmień kolor drewna"}</span>
            </button>
          </div>
        </div>
      </section>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
