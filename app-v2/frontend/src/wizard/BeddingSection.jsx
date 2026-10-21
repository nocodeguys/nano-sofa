import React from "react";
import { NS_DATA } from "../data.jsx";
import { Section } from "./Section.jsx";

const { BEDDING_PRESETS, THROW_PRESETS, TIDY_LEVELS, DENSITY_LEVELS, BED_ACCENTS } = NS_DATA;

/* 10 — bed styling (beds only). Sent to the server as the BEDDING block. */
export function BeddingSection({ st, set }) {
  if (st.kind !== "bed") return null;

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

}
