/*
  Shared by /meli (one photo) and /meli-batch (many photos): the keys, the
  engine + model choice, the wood-colour picker and the form fields both pages
  post to /api/meli/recolor. A page adds only its own photo section, stage and
  run loop.
*/
import React, { useState, useEffect, useRef, useMemo } from "react";

const OR_KEY_STORAGE = "nano-sofa-v2-openrouter-key"; // shared with /editorial and /lab
const GOOGLE_KEY_STORAGE = "nano-sofa-v2-api-key";      // shared with the studio page and /editorial
const ENGINE_STORAGE = "nano-sofa-v2-meli-engine";       // "gemini" | "openrouter"
const MAX_CUSTOM_REFS = 4;
// Coverage levels (server: studio/meli.py OPACITY_LEVELS) — how much grain
// shows through the new colour. "auto" = copy it from the finish photographs.
const OPACITY_HINTS = {
  10: "olej / bezbarwny — słoje w pełni, naturalny ton drewna prześwituje",
  30: "bejca — słoje wyraźne, zmienia się cały odcień",
  55: "lazura półkryjąca — kolor dominuje, słoje przebijają przez pigment",
  80: "farba kryjąca — słoje tylko jako delikatna faktura w świetle",
  100: "gładki lakier — bez widocznych słojów",
};
const DEFAULT_LEVELS = [10, 30, 55, 80, 100].map(v => ({ value: v, name: String(v) }));
const HEX_RE = /^#?[0-9a-fA-F]{6}$/;

export const Ic = {
  sparkle: <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" fill="currentColor"/></svg>,
  upload: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg>,
};

// "Aria 160", "Dąb miodowy" → "aria-160", "dab-miodowy"
export function fileSlug(...parts) {
  return parts.filter(Boolean).join("-").toLowerCase().replace(/ł/g, "l")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function useStored(key, initial) {
  const [value, setValue] = useState(() => {
    try { return localStorage.getItem(key) || initial; } catch { return initial; }
  });
  useEffect(() => {
    try { localStorage.setItem(key, value); } catch {}
  }, [key, value]);
  return [value, setValue];
}

// Everything a Meli recolor needs besides the photo itself.
export function useMeliSetup() {
  // ---- keys: OpenRouter or Google (Nano Banana direct) ----------------------
  const [orKey, setOrKey] = useStored(OR_KEY_STORAGE, "");
  const [googleKey, setGoogleKey] = useStored(GOOGLE_KEY_STORAGE, "");
  const [engine, setEngine] = useState(() => {
    try {
      const saved = localStorage.getItem(ENGINE_STORAGE);
      if (saved === "gemini" || saved === "openrouter") return saved;
      // First visit: whichever key the user already has; Google wins a tie.
      if (localStorage.getItem(GOOGLE_KEY_STORAGE)) return "gemini";
      if (localStorage.getItem(OR_KEY_STORAGE)) return "openrouter";
    } catch {}
    return "gemini";
  });
  useEffect(() => {
    try { localStorage.setItem(ENGINE_STORAGE, engine); } catch {}
  }, [engine]);
  const isGoogle = engine === "gemini";
  const activeKey = isGoogle ? googleKey : orKey;
  const setActiveKey = isGoogle ? setGoogleKey : setOrKey;
  const [showKeyEdit, setShowKeyEdit] = useState(false);

  // ---- palette + models -----------------------------------------------------
  const [palette, setPalette] = useState([]);
  const [levels, setLevels] = useState(DEFAULT_LEVELS);
  const [allModels, setAllModels] = useState([]);
  const [defaults, setDefaults] = useState({ gemini: "", openrouter: "" });
  const [modelId, setModelId] = useState("");
  const [configError, setConfigError] = useState(false);
  useEffect(() => {
    fetch("/api/meli/config").then(r => r.ok ? r.json() : Promise.reject()).then(c => {
      setPalette(c.palette || []);
      if ((c.opacity_levels || []).length) setLevels(c.opacity_levels);
      setAllModels(c.models || []);
      setDefaults({ gemini: c.default_gemini_model || "", openrouter: c.default_model || "" });
    }).catch(() => setConfigError(true));
  }, []);
  const models = useMemo(
    () => allModels.filter(m => (m.engine || "openrouter") === engine),
    [allModels, engine]);
  // Switching engine (or config arriving) → that engine's default model.
  useEffect(() => {
    if (!models.length || models.some(m => m.id === modelId)) return;
    const preferred = defaults[engine];
    setModelId(models.some(m => m.id === preferred) ? preferred : models[0].id);
    // eslint-disable-next-line
  }, [models]);
  useEffect(() => { setShowKeyEdit(!activeKey); /* eslint-disable-next-line */ }, [engine]);
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

  // ---- colour + output ------------------------------------------------------
  const [colorId, setColorId] = useState("");      // "" = own colour
  const [customName, setCustomName] = useState("");
  const [customHex, setCustomHex] = useState("");
  const [opacity, setOpacity] = useState("auto");   // "auto" | level number
  const [customRefs, setCustomRefs] = useState([]); // [{file, url}]
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
  // "wg próbki" only makes sense when finish photographs will be sent.
  const hasSamples = selected ? selected.references.length > 0 : customRefs.length > 0;
  const autoLevel = selected
    ? (selected.opacity ?? (hasSamples ? null : (selected.finish === "opaque" ? 80 : 30)))
    : (hasSamples ? null : 30);
  const effectiveLevel = opacity === "auto" ? autoLevel : opacity;
  const levelName = (v) => (levels.find(l => l.value === v) || {}).name || String(v);
  const opacityLabel = effectiveLevel == null ? "wg próbki" : `${levelName(effectiveLevel)} · ${effectiveLevel}%`;
  const colorLabel = selected ? selected.name_pl : (customName.trim() || customHex.trim() || "");

  const addCustomRefs = (files) => {
    const next = [...customRefs];
    for (const f of files || []) {
      if (next.length >= MAX_CUSTOM_REFS) break;
      next.push({ file: f, url: URL.createObjectURL(f) });
    }
    setCustomRefs(next);
  };

  // The key / colour part of the pre-flight check; null when ready to send.
  const validate = () => {
    if (!activeKey.trim()) {
      return isGoogle
        ? { message: "Wklej klucz Google (AIza…) w sekcji Model.", code: "MISSING_API_KEY" }
        : { message: "Wklej klucz OpenRouter (sk-or-…) w sekcji Model.", code: "MISSING_OPENROUTER_KEY" };
    }
    if (isCustom && !customName.trim() && !HEX_RE.test(customHex.trim()) && !customRefs.length) {
      return { message: "Wybierz kolor z palety albo podaj własny (nazwa, HEX lub zdjęcie próbki).", code: "MISSING_COLOR" };
    }
    return null;
  };

  // Every /api/meli/recolor field except the photo and the product name.
  const appendTo = (fd) => {
    if (isGoogle) fd.append("api_key", googleKey.trim());
    else fd.append("openrouter_key", orKey.trim());
    fd.append("model", modelId);
    if (selected) {
      fd.append("color", selected.id);
    } else {
      // The server needs a name or a HEX; samples alone get a neutral name.
      fd.append("custom_name", customName.trim()
        || (HEX_RE.test(customHex.trim()) ? "" : "the wood colour of the attached finish photographs"));
      fd.append("custom_hex", customHex.trim());
      for (const r of customRefs) fd.append("references", r.file);
    }
    if (opacity !== "auto") fd.append("opacity", String(opacity));
    fd.append("res", res);
    if (quality) fd.append("quality", quality);
  };

  return {
    googleKey, orKey, engine, setEngine, isGoogle, activeKey, setActiveKey, showKeyEdit, setShowKeyEdit,
    palette, levels, models, model, modelId, setModelId, groups, configError,
    colorId, setColorId, customName, setCustomName, customHex, setCustomHex,
    opacity, setOpacity, customRefs, setCustomRefs, addCustomRefs,
    res, setRes, quality, setQuality,
    selected, isCustom, hasSamples, autoLevel, effectiveLevel, levelName, opacityLabel, colorLabel,
    validate, appendTo,
  };
}

export function MeliErrors({ s, error }) {
  // The run button sits at the bottom of a long form — bring the reason up.
  const boxRef = useRef(null);
  useEffect(() => {
    if (error && boxRef.current) boxRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [error]);
  return (
    <>
      {s.configError && (
        <div className="ed-err"><strong>CONFIG</strong> — nie udało się pobrać palety Meli z serwera.</div>
      )}
      {error && (
        <div className="ed-err" ref={boxRef}>
          <strong>{error.code || "Błąd"}</strong> — {error.message}
          {error.detail && (
            <div style={{ marginTop: 6, fontFamily: "'Geist Mono', monospace", fontSize: 11, opacity: .8, wordBreak: "break-word" }}>
              Szczegóły od {s.isGoogle ? "Google" : "OpenRouter"}: {error.detail}
            </div>
          )}
        </div>
      )}
    </>
  );
}

export function MeliColorSection({ num, s }) {
  const refInputRef = useRef(null);
  const { selected, isCustom, customRefs, effectiveLevel, autoLevel, hasSamples } = s;
  return (
    <div className="section">
      <div className="sec-head">
        <div className="num">{num}</div>
        <div className="title serif">Kolor drewna</div>
        <div className="summary">{s.colorLabel || (customRefs.length ? "wg próbki" : "wybierz")}</div>
      </div>
      <p className="sec-help">Kolory Meli mają przypisane zdjęcia próbek — trafiają do modelu jako referencja barwy i wykończenia.</p>
      <div className="sec-body">
        {s.palette.length === 0 && !s.configError && (
          <div className="hint" style={{ marginTop: 0, marginBottom: 10 }}>
            paleta Meli jest jeszcze pusta — użyj własnego koloru poniżej
          </div>
        )}
        {s.groups.map(g => (
          <div key={g.key || "_"} style={{ marginBottom: 10 }}>
            {g.key && <div className="field-lbl" style={{ fontSize: 10, opacity: .8 }}>{g.key}</div>}
            <div className="meli-sw">
              {g.colors.map(c => (
                <button key={c.id} className={s.colorId === c.id ? "on" : ""} onClick={() => s.setColorId(c.id)}
                  title={`${c.name_pl}${c.references.length ? ` · ${c.references.length} zdj.` : ""}`}>
                  <span className="chip" style={c.references.length
                    ? { backgroundImage: `url(${c.references[0]})` }
                    : { background: c.hex || "#c9b79c" }} />
                  <span className="nm">{c.name_pl}</span>
                </button>
              ))}
            </div>
          </div>
        ))}

        <button className={"meli-own " + (isCustom ? "on" : "")} onClick={() => s.setColorId("")}>
          własny kolor / próbka
        </button>
        {isCustom && (
          <div style={{ marginTop: 10 }}>
            <div className="field-lbl">nazwa / opis koloru</div>
            <input className="input" placeholder="np. ciepły orzech z miodowym podtonem"
              value={s.customName} onChange={e => s.setCustomName(e.target.value)} />
            <div className="field-lbl" style={{ marginTop: 12 }}>HEX (opcjonalnie)</div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="color" value={/^#[0-9a-fA-F]{6}$/.test(s.customHex) ? s.customHex : "#a67b5b"}
                onChange={e => s.setCustomHex(e.target.value.toUpperCase())}
                style={{ width: 38, height: 34, padding: 0, border: "1px solid var(--line-2)", borderRadius: 8, background: "none" }} />
              <input className="input" placeholder="#A67B5B" value={s.customHex} maxLength={7}
                onChange={e => s.setCustomHex(e.target.value)} style={{ maxWidth: 140, fontFamily: "Geist Mono" }} />
              {s.customHex && <button className="meli-own" onClick={() => s.setCustomHex("")}>wyczyść</button>}
            </div>
            <div className="field-lbl" style={{ marginTop: 12 }}>zdjęcia próbki (opcjonalnie, do {MAX_CUSTOM_REFS})</div>
            <div className="ed-refs">
              {customRefs.map((r, i) => (
                <div key={r.url} className="slot">
                  <img src={r.url} alt={`próbka ${i + 1}`} />
                  <button type="button" className="x" onClick={() => s.setCustomRefs(customRefs.filter((_, j) => j !== i))}>×</button>
                </div>
              ))}
              {customRefs.length < MAX_CUSTOM_REFS && (
                <div className="slot" onClick={() => refInputRef.current && refInputRef.current.click()}>＋</div>
              )}
            </div>
            <input ref={refInputRef} type="file" accept="image/*" multiple style={{ display: "none" }}
              onChange={e => { s.addCustomRefs(e.target.files); e.target.value = ""; }} />
          </div>
        )}
        {selected && (
          <div className="hint">
            {selected.hex ? `${selected.hex} · ` : ""}
            {selected.references.length ? selected.references.length + " zdj. próbki" : "bez zdjęcia próbki"}
          </div>
        )}

        <div className="field-lbl" style={{ marginTop: 16 }}>poziom krycia</div>
        <div className="seg">
          <button className={s.opacity === "auto" ? "on" : ""} onClick={() => s.setOpacity("auto")}
            title={hasSamples ? "widoczność słojów jak na zdjęciach próbki" : "domyślny poziom koloru"}>
            {hasSamples && autoLevel == null ? "wg próbki" : `domyślny (${s.levelName(autoLevel)})`}
          </button>
          {s.levels.map(l => (
            <button key={l.value} className={s.opacity === l.value ? "on" : ""} onClick={() => s.setOpacity(l.value)}>
              {l.name}
            </button>
          ))}
        </div>
        <div className="meli-opacity" aria-hidden="true">
          <span style={{ width: `${effectiveLevel == null ? 50 : effectiveLevel}%`, opacity: effectiveLevel == null ? .35 : 1 }} />
        </div>
        <div className="hint">
          {effectiveLevel == null
            ? "słoje przebijają tak jak na zdjęciach próbki — zdjęcia są wzorcem krycia"
            : `${effectiveLevel}% · ${OPACITY_HINTS[effectiveLevel] || ""}`}
          {effectiveLevel != null && effectiveLevel <= 55 ? " · na malowanym drewnie model dorysuje słoje" : ""}
        </div>
      </div>
    </div>
  );
}

// `fixedSize`: the page sends match_source, so the resolution follows each
// photo and the picker would be a lie.
export function MeliModelSection({ num, s, fixedSize = false }) {
  const { isGoogle, model, activeKey } = s;
  return (
    <div className="section">
      <div className="sec-head">
        <div className="num">{num}</div>
        <div className="title serif">Model</div>
        <div className="summary">{fixedSize ? "rozmiar zdjęcia" : s.res}{s.quality ? ` · ${s.quality}` : ""}</div>
      </div>
      <p className="sec-help">
        {isGoogle
          ? "Nano Banana bezpośrednio od Google, na Twoim kluczu Google AI Studio — ten sam klucz co w Studio."
          : "Wszystkie modele obrazowe z OpenRouter. Najwierniej edytują zdjęcie Nano Banana i GPT Image; FLUX / Seedream / Krea potrafią przerysować łóżko."}
      </p>
      <div className="sec-body">
        <div className="field-lbl">dostawca</div>
        <div className="seg" style={{ marginBottom: 12 }}>
          <button className={isGoogle ? "on" : ""} onClick={() => s.setEngine("gemini")}>Google · Nano Banana</button>
          <button className={isGoogle ? "" : "on"} onClick={() => s.setEngine("openrouter")}>OpenRouter</button>
        </div>
        <select className="select" value={s.modelId} onChange={e => s.setModelId(e.target.value)}>
          {s.models.map(m => (
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
                <button key={q} className={s.quality === q ? "on" : ""} onClick={() => s.setQuality(q)}>{q}</button>
              ))}
            </div>
          </>
        )}
        {fixedSize ? (
          <div className="hint" style={{ marginTop: 14 }}>
            rozdzielczość dobierana do każdego zdjęcia — wynik wraca w jego proporcjach i rozmiarze w pikselach
          </div>
        ) : model && (model.resolutions || []).length > 0 && model.resolutions[0] !== "auto" && (
          <>
            <div className="field-lbl" style={{ marginTop: 14 }}>rozdzielczość</div>
            <div className="seg">
              {model.resolutions.map(r => (
                <button key={r} className={s.res === r ? "on" : ""} onClick={() => s.setRes(r)}>{r}</button>
              ))}
            </div>
          </>
        )}

        <div className="field-lbl" style={{ marginTop: 14 }}>{isGoogle ? "klucz Google (Gemini API)" : "klucz OpenRouter"}</div>
        {s.showKeyEdit || !activeKey ? (
          <input type="password" className="input" placeholder={isGoogle ? "AIza…" : "sk-or-…"} value={activeKey}
            onChange={e => s.setActiveKey(e.target.value)}
            onBlur={() => activeKey && s.setShowKeyEdit(false)}
            style={{ fontFamily: "Geist Mono", fontSize: 13 }} />
        ) : (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="mono" style={{ fontSize: 12 }}>{isGoogle ? "AIza" : "sk-or-"}…{activeKey.slice(-4)}</span>
            <button className="meli-own" onClick={() => s.setShowKeyEdit(true)}>zmień</button>
          </div>
        )}
        <div className="hint">
          {isGoogle ? (
            <>trzymany tylko w tej przeglądarce, ten sam co w Studio i Editorial · pobierz z{" "}
              <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">aistudio.google.com/apikey</a></>
          ) : (
            <>trzymany tylko w tej przeglądarce, ten sam co w Editorial i Lab · pobierz z{" "}
              <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noreferrer">openrouter.ai/settings/keys</a></>
          )}
        </div>
      </div>
    </div>
  );
}
