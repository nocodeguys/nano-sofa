import React, { useRef } from "react";
import { NS_DATA, Ic } from "../data.jsx";
import { Section } from "./Section.jsx";

const { BACKGROUNDS } = NS_DATA;

/* 01 — background: ONE picker for studio backdrop / interior / own photo.
   `pickBackground` seeds the camera defaults when moving onto / off a locked
   backdrop (see App); the component owns only the file input ref. */
export function BackgroundSection({ st, set, bgObj, bgLocked, pickBackground, setLockBackground }) {
  const envFileRef = useRef(null);
  return (
<Section num="01" title="Tło"
  summary={bgObj ? `${bgObj.name}${bgLocked ? " · katalog" : ""}` : "—"}
  help="Jedno miejsce na tło. Cyklorama to studio — te z dopiskiem „katalog” blokują światło, obiektyw i wysokość kamery, a render jest potem normalizowany do profilu. Wnętrze to scena lifestyle. Własne zdjęcie wgrywasz tutaj.">
  {(() => {
    const groups = [
      { key: "backdrop", label: "Cyklorama / studio", sub: "jednolite tło, cień kontaktowy" },
      { key: "scene",    label: "Wnętrze",            sub: "aranżowana scena lifestyle" },
      { key: "custom",   label: "Własne zdjęcie",     sub: "Twoje zdjęcie jako scena" },
    ].map(g => ({ ...g, items: BACKGROUNDS.filter(b => b.kind === g.key) }));
    const activeKind = bgObj?.kind || "backdrop";
    const group = groups.find(g => g.key === activeKind) || groups[0];
    return (<>
      <div className="mode-switch" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        {groups.map(g => (
          <button type="button" key={g.key} className={activeKind === g.key ? "selected" : ""}
            onClick={() => {
              const first = g.items[0];
              if (first) { pickBackground(first); set({ refsLock: false }); }
              setLockBackground(false);
            }}>
            <span className="mode-title">{g.label}</span>
            <span className="mode-sub">{g.sub}</span>
          </button>
        ))}
      </div>

      <div className="env-grid" style={{ marginTop: 12 }}>
        {group.items.map(b => (
          <div key={b.id}
            className={"env " + (st.bg === b.id ? "sel " : "") + (b.transparent ? "checker" : "")}
            onClick={() => pickBackground(b)}>
            <div className="env-thumb" style={{ background: b.preview }}>
              {b.kind === "scene" && (<>
                <div className="floor" style={{ background: b.acc }}></div>
                <div className="prop"></div>
              </>)}
              {b.kind === "custom" && <div className="upload-icon">+</div>}
            </div>
            <div className="env-meta">
              <div className="env-name">{b.name}{b.locked ? " · katalog" : ""}</div>
              <div className="env-prop">{b.kind === "backdrop" ? (b.hex || "PNG z alfą") : b.prop}</div>
            </div>
          </div>
        ))}
      </div>

      {bgObj?.note && (
        <div style={{ fontSize: 10, color: "var(--ink-3)", marginTop: 6, fontFamily: "Geist Mono", lineHeight: 1.5 }}>
          {bgObj.note}
        </div>
      )}
      {bgLocked && (
        <div style={{
          marginTop: 10, padding: "9px 11px", borderRadius: 8,
          background: "var(--bg-1)", border: "1px solid var(--line-2)",
          fontSize: 10.5, color: "var(--ink-2)", lineHeight: 1.5,
        }}>
          <strong style={{ fontWeight: 650 }}>Tło katalogowe:</strong>{" "}
          światło jest zablokowane (południe, miękkie cienie), a render hero jest
          normalizowany do profilu. Kadr, obiektyw, głębia i region detalu są Twoje —
          obiektyw startuje od 85 mm, f/8; kontrakt kadrowania działa dla ujęcia hero.
        </div>
      )}

      {st.bg === "custom" && (
        <div className="env-custom">
          <div className="head">
            <span className="ico">{Ic.upload}</span>
            <div style={{ flex: 1 }}>
              <div className="lead">{(st.bgFile && st.bgFile.name) || "Wgraj zdjęcie tła"}</div>
              <div className="sub">{st.bgFile ? "kliknij aby zmienić" : "model umieści produkt w tym wnętrzu i dopasuje światło"}</div>
            </div>
            <input ref={envFileRef} type="file" accept="image/*" style={{ display: "none" }}
              onChange={e => { const f = e.target.files?.[0]; if (f) set({ bgFile: f }); }} />
            <button className="size-pill" onClick={() => {
              if (st.bgFile) { set({ bgFile: null }); return; }
              envFileRef.current?.click();
            }}>
              {st.bgFile ? "usuń" : "wybierz plik"}
            </button>
          </div>
          <div style={{ marginTop: 10 }}>
            <div className="field-lbl">notatka</div>
            <input className="input" placeholder="np. salon na poddaszu, popołudnie"
              value={st.bgNote} onChange={e => set({ bgNote: e.target.value })} />
          </div>
        </div>
      )}
    </>);
  })()}
</Section>
  );
}
