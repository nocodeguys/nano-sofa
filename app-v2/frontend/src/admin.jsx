import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import "./styles-v2.css";
import "./admin.css";
import { NanoTopbar } from "./header.jsx";

const clone = value => JSON.parse(JSON.stringify(value));

function errorMessage(error, fallback = "Nie udało się wykonać operacji.") {
  if (error?.detail) return error.detail;
  if (error?.message) return error.message;
  return fallback;
}

async function readJson(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `Błąd serwera (${response.status})`);
  return body;
}

function Field({ label, hint, wide, children }) {
  return (
    <label className={wide ? "admin-field wide" : "admin-field"}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

function ReferencePanel({ title, description, alt, reference, pendingFile, deleted, onFile, onDelete }) {
  const preview = useMemo(() => {
    if (pendingFile) return URL.createObjectURL(pendingFile);
    return deleted ? null : reference?.url;
  }, [pendingFile, deleted, reference?.url]);
  useEffect(() => () => {
    if (pendingFile && preview) URL.revokeObjectURL(preview);
  }, [pendingFile, preview]);

  return (
    <div className="reference-panel">
      <div className="reference-preview">
        {preview ? <img src={preview} alt={alt} /> : <span>brak<br />referencji</span>}
      </div>
      <div className="reference-actions">
        <strong>{title}</strong>
        <p>{description}</p>
        <label className="admin-button secondary file-button">
          {preview ? "Zamień zdjęcie" : "Dodaj zdjęcie"}
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={event => onFile(event.target.files?.[0] || null)} />
        </label>
        {preview && <button className="admin-text-button danger" type="button" onClick={onDelete}>Usuń referencję</button>}
        {pendingFile && <span className="pending-note">nowy plik: {pendingFile.name}</span>}
      </div>
    </div>
  );
}

function MaterialCard({
  material,
  reference,
  applicationReference,
  viewReferences,
  pendingFile,
  pendingApplicationFile,
  pendingViewFiles,
  deleted,
  applicationDeleted,
  deletedViewKeys,
  onChange,
  onFile,
  onApplicationFile,
  onViewFile,
  onDeleteReference,
  onDeleteApplicationReference,
  onDeleteViewReference,
}) {
  const [open, setOpen] = useState(material.id === "boucle");

  const patch = values => onChange({ ...material, ...values });
  const avoidText = (material.avoid_en || []).join("\n");

  return (
    <article className={"material-card" + (open ? " open" : "")}>
      <button className="material-head" type="button" onClick={() => setOpen(value => !value)}>
        <div className={"material-mini mat-" + material.tex}><span className={"fabric-overlay " + material.tex}></span></div>
        <div>
          <strong>{material.name_pl}</strong>
          <span>{material.prop_pl} · {material.finish_pl}</span>
        </div>
        <code>{material.id}</code>
        <span className="material-caret">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="material-body">
          <div className="reference-stack">
            <ReferencePanel
              title="Wzorzec faktury"
              description="Makro lub płaska próbka. Model kopiuje z niej mikrosplot i skalę, bez koloru i geometrii."
              alt={`Wzorzec faktury ${material.name_pl}`}
              reference={reference}
              pendingFile={pendingFile}
              deleted={deleted}
              onFile={onFile}
              onDelete={onDeleteReference}
            />
            <ReferencePanel
              title="Widok pod kątem — lewa strona"
              description="Płaska próbka oglądana z lewej. Razem z prawym kątem pokazuje kierunkowy połysk i relief włókien."
              alt={`Lewy kąt ${material.name_pl}`}
              reference={viewReferences?.left}
              pendingFile={pendingViewFiles?.left}
              deleted={deletedViewKeys?.has(`${material.id}:left`)}
              onFile={file => onViewFile("left", file)}
              onDelete={() => onDeleteViewReference("left")}
            />
            <ReferencePanel
              title="Widok pod kątem — prawa strona"
              description="Płaska próbka oglądana z prawej. Model porównuje oba kąty zamiast kopiować jedno ustawienie światła."
              alt={`Prawy kąt ${material.name_pl}`}
              reference={viewReferences?.right}
              pendingFile={pendingViewFiles?.right}
              deleted={deletedViewKeys?.has(`${material.id}:right`)}
              onFile={file => onViewFile("right", file)}
              onDelete={() => onDeleteViewReference("right")}
            />
            <ReferencePanel
              title="Zagięcie / zachowanie materiału"
              description="Próbka na krzywiźnie lub zagnieceniu. Pokazuje zmianę włosa, mikrocienie i zachowanie skali splotu na załamaniu."
              alt={`Zagięcie ${material.name_pl}`}
              reference={viewReferences?.behavior}
              pendingFile={pendingViewFiles?.behavior}
              deleted={deletedViewKeys?.has(`${material.id}:behavior`)}
              onFile={file => onViewFile("behavior", file)}
              onDelete={() => onDeleteViewReference("behavior")}
            />
            <ReferencePanel
              title="Materiał na meblu / konkurencja"
              description="Zdjęcie pełnego mebla pokazujące wygląd tkaniny z dystansu. Model nie może kopiować bryły, szwów, pikowania, wnętrza ani stylizacji konkurencji."
              alt={`Materiał ${material.name_pl} na meblu`}
              reference={applicationReference}
              pendingFile={pendingApplicationFile}
              deleted={applicationDeleted}
              onFile={onApplicationFile}
              onDelete={onDeleteApplicationReference}
            />
          </div>

          <div className="admin-grid material-fields">
            <Field label="Nazwa w panelu">
              <input value={material.name_pl} onChange={event => patch({ name_pl: event.target.value })} />
            </Field>
            <Field label="Krótki opis">
              <input value={material.prop_pl} onChange={event => patch({ prop_pl: event.target.value })} />
            </Field>
            <Field label="Wykończenie">
              <input value={material.finish_pl} onChange={event => patch({ finish_pl: event.target.value })} />
            </Field>
            <Field label="Typ podglądu CSS" hint="Wpływa tylko na próbkę w konfiguratorze.">
              <select value={material.tex} onChange={event => patch({ tex: event.target.value })}>
                {["linen", "boucle", "weave", "chenille", "cremona", "leather", "velvet"].map(value => <option key={value}>{value}</option>)}
              </select>
            </Field>
            <Field wide label="Nazwa dla modelu (EN)" hint="To krótkie określenie ma duży wpływ na interpretację materiału.">
              <input value={material.noun_en} onChange={event => patch({ noun_en: event.target.value })} />
            </Field>
            <Field wide label="Opis faktury dla modelu (EN)" hint="Opisz skalę splotu, relief, włókna, matowość i zachowanie światła.">
              <textarea rows="7" value={material.texture_en} onChange={event => patch({ texture_en: event.target.value })} />
            </Field>
            <Field wide label="Czego model ma unikać (EN)" hint="Jedno wykluczenie w każdym wierszu.">
              <textarea rows="4" value={avoidText} onChange={event => patch({ avoid_en: event.target.value.split("\n") })} />
            </Field>
          </div>
        </div>
      )}
    </article>
  );
}

function ColorCard({ color, canDelete, onChange, onDelete }) {
  const patch = values => onChange({ ...color, ...values });
  return (
    <article className="color-card">
      <div className="color-card-head">
        <input className="color-picker" type="color" value={color.hex} onChange={event => patch({ hex: event.target.value.toUpperCase() })} />
        <div><strong>{color.name_pl || "Nowy kolor"}</strong><code>{color.id || "bez-id"}</code></div>
        {canDelete && <button className="icon-delete" type="button" title="Usuń kolor" onClick={onDelete}>×</button>}
      </div>
      <div className="admin-grid color-fields">
        <Field label="ID" hint="Małe litery, bez spacji.">
          <input value={color.id} disabled={color.id === "greige"} onChange={event => patch({ id: event.target.value.toLowerCase().replace(/\s+/g, "-") })} />
        </Field>
        <Field label="Nazwa po polsku">
          <input value={color.name_pl} onChange={event => patch({ name_pl: event.target.value })} />
        </Field>
        <Field label="HEX">
          <input value={color.hex} onChange={event => patch({ hex: event.target.value.toUpperCase() })} />
        </Field>
        <Field label="Numery / kolekcje próbek">
          <input value={color.covers || ""} onChange={event => patch({ covers: event.target.value })} />
        </Field>
        <Field wide label="Opis koloru dla modelu (EN)" hint="Najlepiej: nazwa, podton oraz wartość HEX.">
          <textarea rows="3" value={color.prompt_en} onChange={event => patch({ prompt_en: event.target.value })} />
        </Field>
      </div>
    </article>
  );
}

function AdminApp() {
  const [payload, setPayload] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [baseline, setBaseline] = useState("");
  const [tab, setTab] = useState("materials");
  const [pendingRefs, setPendingRefs] = useState({});
  const [deletedRefs, setDeletedRefs] = useState(new Set());
  const [pendingApplicationRefs, setPendingApplicationRefs] = useState({});
  const [deletedApplicationRefs, setDeletedApplicationRefs] = useState(new Set());
  const [pendingViewRefs, setPendingViewRefs] = useState({});
  const [deletedViewRefs, setDeletedViewRefs] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState({ type: "", text: "" });
  const [buildState, setBuildState] = useState(null);
  const statusTimer = useRef(null);

  const load = async () => {
    try {
      const data = await readJson(await fetch("/api/admin/catalog", { cache: "no-store" }));
      const next = clone(data.catalog);
      setPayload(data);
      setCatalog(next);
      setBaseline(JSON.stringify(next));
      setBuildState(data.build);
    } catch (error) {
      setStatus({ type: "error", text: errorMessage(error, "Nie udało się wczytać katalogu.") });
    }
  };
  useEffect(() => { load(); }, []);

  const dirty = !!catalog && (
    JSON.stringify(catalog) !== baseline
    || Object.keys(pendingRefs).length > 0
    || deletedRefs.size > 0
    || Object.keys(pendingApplicationRefs).length > 0
    || deletedApplicationRefs.size > 0
    || Object.keys(pendingViewRefs).length > 0
    || deletedViewRefs.size > 0
  );
  useEffect(() => {
    const handler = event => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const updateMaterial = (index, item) => setCatalog(current => ({
    ...current,
    materials: current.materials.map((value, i) => i === index ? item : value),
  }));
  const updateColor = (index, item) => setCatalog(current => ({
    ...current,
    colors: current.colors.map((value, i) => i === index ? item : value),
  }));
  const setReference = (id, file) => {
    if (!file) return;
    setPendingRefs(current => ({ ...current, [id]: file }));
    setDeletedRefs(current => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  };
  const deleteReference = id => {
    setPendingRefs(current => {
      const next = { ...current };
      delete next[id];
      return next;
    });
    setDeletedRefs(current => new Set(current).add(id));
  };
  const setApplicationReference = (id, file) => {
    if (!file) return;
    setPendingApplicationRefs(current => ({ ...current, [id]: file }));
    setDeletedApplicationRefs(current => {
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  };
  const deleteApplicationReference = id => {
    setPendingApplicationRefs(current => {
      const next = { ...current };
      delete next[id];
      return next;
    });
    setDeletedApplicationRefs(current => new Set(current).add(id));
  };
  const setViewReference = (id, role, file) => {
    if (!file) return;
    const key = `${id}:${role}`;
    setPendingViewRefs(current => ({ ...current, [key]: file }));
    setDeletedViewRefs(current => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  };
  const deleteViewReference = (id, role) => {
    const key = `${id}:${role}`;
    setPendingViewRefs(current => {
      const next = { ...current };
      delete next[key];
      return next;
    });
    setDeletedViewRefs(current => new Set(current).add(key));
  };
  const addColor = () => setCatalog(current => ({
    ...current,
    colors: [...current.colors, {
      id: `kolor-${current.colors.length + 1}`,
      name_pl: "nowy kolor",
      hex: "#C8C3BA",
      fabric: true,
      covers: "",
      prompt_en: "neutral upholstery colour (hex #C8C3BA)",
    }],
  }));

  const startStatusPolling = () => {
    clearInterval(statusTimer.current);
    statusTimer.current = setInterval(async () => {
      try {
        const next = await readJson(await fetch("/api/admin/status", { cache: "no-store" }));
        setBuildState(next);
      } catch {}
    }, 700);
  };

  const save = async () => {
    if (!dirty || busy) return;
    setBusy(true);
    setStatus({ type: "working", text: "Sprawdzam dane…" });
    startStatusPolling();
    try {
      const body = new FormData();
      body.append("catalog_json", JSON.stringify(catalog));
      Object.entries(pendingRefs).forEach(([id, file]) => {
        body.append("reference_ids", id);
        body.append("reference_files", file, file.name);
      });
      body.append("delete_reference_ids_json", JSON.stringify([...deletedRefs]));
      Object.entries(pendingApplicationRefs).forEach(([id, file]) => {
        body.append("application_reference_ids", id);
        body.append("application_reference_files", file, file.name);
      });
      body.append(
        "delete_application_reference_ids_json",
        JSON.stringify([...deletedApplicationRefs]),
      );
      Object.entries(pendingViewRefs).forEach(([key, file]) => {
        body.append("view_reference_keys", key);
        body.append("view_reference_files", file, file.name);
      });
      body.append(
        "delete_view_reference_keys_json",
        JSON.stringify([...deletedViewRefs]),
      );
      const data = await readJson(await fetch("/api/admin/catalog", { method: "POST", body }));
      const next = clone(data.catalog);
      setPayload(data);
      setCatalog(next);
      setBaseline(JSON.stringify(next));
      setPendingRefs({});
      setDeletedRefs(new Set());
      setPendingApplicationRefs({});
      setDeletedApplicationRefs(new Set());
      setPendingViewRefs({});
      setDeletedViewRefs(new Set());
      setBuildState(data.build);
      setStatus({
        type: "success",
        text: `Gotowe. Katalog został sprawdzony, aplikacja przebudowana, a backend przeładowany. Backup: ${data.backup}.`,
      });
    } catch (error) {
      setStatus({ type: "error", text: errorMessage(error) });
    } finally {
      clearInterval(statusTimer.current);
      setBusy(false);
    }
  };

  if (!catalog) {
    return (
      <div className="app-frame">
        <NanoTopbar active="admin" hideApiKey />
        <main className="admin-loading">{status.text || "Ładuję katalog…"}</main>
      </div>
    );
  }

  return (
    <div className="app-frame admin-frame">
      <NanoTopbar active="admin" hideApiKey />
      <main className="admin-shell">
        <header className="admin-hero">
          <div>
            <span className="admin-eyebrow">ŹRÓDŁO PRAWDY · CATALOG.JSON</span>
            <h1>Materiały i kolory</h1>
            <p>Zmieniasz dane, które widzi konfigurator i model. Zapis zawsze uruchamia walidację, kontrolny build oraz przeładowanie katalogu.</p>
          </div>
          <div className="admin-health">
            <span className={"health-dot " + (buildState?.state || "idle")}></span>
            <div><strong>{buildState?.message || "Gotowy"}</strong><small>{catalog.materials.length} tkanin · {catalog.colors.length} kolorów</small></div>
          </div>
        </header>

        <div className="admin-tabs">
          <button className={tab === "materials" ? "on" : ""} onClick={() => setTab("materials")}>Tkaniny <span>{catalog.materials.length}</span></button>
          <button className={tab === "colors" ? "on" : ""} onClick={() => setTab("colors")}>Kolory <span>{catalog.colors.length}</span></button>
        </div>

        {tab === "materials" ? (
          <section className="admin-list">
            <div className="section-intro">
              <div><h2>Tkaniny</h2><p>Opisy i zdjęcia wzorcowe są razem. ID tkanin są zablokowane przez schemat generatora.</p></div>
            </div>
            {catalog.materials.map((material, index) => (
              <MaterialCard
                key={material.id}
                material={material}
                reference={payload.references?.[material.id]}
                applicationReference={payload.application_references?.[material.id]}
                viewReferences={payload.view_references?.[material.id]}
                pendingFile={pendingRefs[material.id]}
                pendingApplicationFile={pendingApplicationRefs[material.id]}
                pendingViewFiles={{
                  left: pendingViewRefs[`${material.id}:left`],
                  right: pendingViewRefs[`${material.id}:right`],
                  behavior: pendingViewRefs[`${material.id}:behavior`],
                }}
                deleted={deletedRefs.has(material.id)}
                applicationDeleted={deletedApplicationRefs.has(material.id)}
                deletedViewKeys={deletedViewRefs}
                onChange={item => updateMaterial(index, item)}
                onFile={file => setReference(material.id, file)}
                onApplicationFile={file => setApplicationReference(material.id, file)}
                onViewFile={(role, file) => setViewReference(material.id, role, file)}
                onDeleteReference={() => deleteReference(material.id)}
                onDeleteApplicationReference={() => deleteApplicationReference(material.id)}
                onDeleteViewReference={role => deleteViewReference(material.id, role)}
              />
            ))}
          </section>
        ) : (
          <section className="admin-list">
            <div className="section-intro">
              <div><h2>Paleta kolorów</h2><p>HEX kotwiczy odcień, a angielski opis doprecyzowuje podton i charakter koloru.</p></div>
              <button className="admin-button secondary" type="button" onClick={addColor}>+ Dodaj kolor</button>
            </div>
            <div className="color-list">
              {catalog.colors.map((color, index) => (
                <ColorCard
                  key={`${color.id}-${index}`}
                  color={color}
                  canDelete={color.id !== "greige"}
                  onChange={item => updateColor(index, item)}
                  onDelete={() => setCatalog(current => ({ ...current, colors: current.colors.filter((_, i) => i !== index) }))}
                />
              ))}
            </div>
          </section>
        )}
      </main>

      <footer className="admin-savebar">
        <div className={"save-message " + status.type}>
          {status.text || (dirty ? "Masz niezapisane zmiany." : "Katalog jest zsynchronizowany z aplikacją.")}
        </div>
        <div className="save-actions">
          <a className="admin-button secondary" href="/" target="_blank" rel="noreferrer">Otwórz Studio ↗</a>
          <button className="admin-button primary" type="button" disabled={!dirty || busy} onClick={save}>
            {busy ? "Zapisuję…" : "Zapisz katalog"}
          </button>
        </div>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<AdminApp />);
