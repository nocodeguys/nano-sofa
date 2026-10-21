import React from "react";
import { Ic } from "../data.jsx";
import { Section } from "./Section.jsx";

/* 09 — moodboard references (never under a locked backdrop: the server strips
   them there). `budget` is the reference budget from wizard/request.js. */
export function ReferencesSection({ st, set, bgLocked, modelObj, refFileRef, refSlotRef, onPickRef, clearRef, fmtSize, budget }) {
  if (bgLocked) return null;

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
      {budget && (
        <div style={{
          marginBottom: 10, padding: "8px 11px", borderRadius: 8,
          background: "var(--bg-1)", border: "1px solid var(--line-2)",
          fontSize: 11, lineHeight: 1.5, color: "var(--ink-2)",
        }}>
          <strong style={{ fontWeight: 650 }}>Do modelu pójdzie {budget.attached.length} z {budget.cap}:</strong>{" "}
          {budget.attached.map((r, i) => `${i + 1}. ${r.label}`).join(" · ")}
          {budget.dropped.length > 0 && (
            <span style={{ color: "var(--warn, #a33a2e)" }}>
              {" "}— {budget.dropped.length} ponad limit modelu ({budget.dropped.map(r => r.label).join(", ")})
            </span>
          )}
        </div>
      )}
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
          cursor: (filled > 0 && !bgLocked) ? "pointer" : "not-allowed",
          opacity: (filled > 0 && !bgLocked) ? 1 : 0.55,
          fontSize:12.5, lineHeight:1.45,
        }}>
          <input
            type="checkbox"
            checked={filled > 0 && !!st.refsLock && !bgLocked}
            disabled={filled === 0 || bgLocked}
            onChange={e => set({ refsLock: e.target.checked })}
            style={{marginTop:2, flexShrink:0}} />
          <span>
            <strong style={{fontWeight:600}}>Użyj referencji jako wzorca</strong>
            {bgLocked
              ? " — wyłączone, ponieważ profil katalogowy korzysta z własnej referencji pustego studia."
              : filled === 0
              ? " — wgraj najpierw referencję w slot powyżej, żeby włączyć tę opcję."
              : " — "}
            {filled > 0 && !bgLocked && (
              <>
                referencja staje się źródłem prawdy dla kąta kamery,
                kadrowania, oświetlenia, cieni i sceny. Ustawienia z sekcji{" "}
                <span style={{fontFamily:"'Geist Mono', monospace"}}>04 Ujęcie</span>{", "}
                <span style={{fontFamily:"'Geist Mono', monospace"}}>06 Otoczenie</span>{" oraz "}
                <span style={{fontFamily:"'Geist Mono', monospace"}}>08 Kamera (światło)</span>
                {" "}są wtedy ignorowane. Kolor, materiał, nogi i rozmiar nadal pochodzą z kreatora.
              </>
            )}
          </span>
        </label>
      ) : null}
    </Section>
  );

}
