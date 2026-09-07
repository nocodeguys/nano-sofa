import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import "./styles-v2.css";
import "./admin.css";
import { NanoTopbar } from "./header.jsx";

const TOKEN_STORAGE = "nano-sofa-admin-token";
const clone = value => JSON.parse(JSON.stringify(value));

function errorMessage(error, fallback = "Nie udało się wykonać operacji.") {
  if (error?.detail) return error.detail;
  if (error?.message) return error.message;
  return fallback;
}

function readToken() {
  try { return localStorage.getItem(TOKEN_STORAGE) || ""; } catch { return ""; }
}
function storeToken(value) {
  try { if (value) localStorage.setItem(TOKEN_STORAGE, value); else localStorage.removeItem(TOKEN_STORAGE); } catch {}
}

// Every admin call carries the token (when one is stored). A 401 means the
// server wants ADMIN_TOKEN and ours is missing or wrong — the gate screen
// takes over. A 403 is the loopback-only refusal in a Docker deployment
// without a token: the message tells the operator what to set.
class AuthError extends Error {
  constructor(status, detail) { super(detail); this.status = status; this.detail = detail; }
}
async function adminFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = readToken();
  if (token) headers.set("X-Admin-Token", token);
  const response = await fetch(url, { cache: "no-store", ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (response.status === 401 || response.status === 403) throw new AuthError(response.status, body.detail || "Brak dostępu.");
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

// Admin reference images need the token too — <img src> can't send a header,
// so previews are fetched as blobs and shown through object URLs.
function useAuthedImage(url) {
  const [objectUrl, setObjectUrl] = useState(null);
  useEffect(() => {
    let revoked = false;
    let current = null;
    if (!url) { setObjectUrl(null); return undefined; }
    const headers = {};
    const token = readToken();
    if (token) headers["X-Admin-Token"] = token;
    fetch(url, { headers, cache: "no-store" })
      .then(r => (r.ok ? r.blob() : null))
      .then(blob => {
        if (!blob || revoked) return;
        current = URL.createObjectURL(blob);
        setObjectUrl(current);
      })
      .catch(() => {});
    return () => { revoked = true; if (current) URL.revokeObjectURL(current); };
  }, [url]);
  return objectUrl;
}

function AuthedReference({ reference, ...rest }) {
  const objectUrl = useAuthedImage(reference?.url);
  const resolved = reference ? { ...reference, url: objectUrl } : reference;
  return <ReferencePanel reference={resolved} {...rest} />;
}

function MaterialCard({
  material, knownTex,
  reference, applicationReference, viewReferences,
  pendingFile, pendingApplicationFile, pendingViewFiles,
  deleted, applicationDeleted, deletedViewKeys,
  onChange, onFile, onApplicationFile, onViewFile,
  onDeleteReference, onDeleteApplicationReference, onDeleteViewReference,
}) {
  const [open, setOpen] = useState(material.id === "boucle");
  const patch = values => onChange({ ...material, ...values });
  const avoidText = (material.avoid_en || []).join("\n");
  const texOptions = Array.from(new Set([...(knownTex || []), material.tex].filter(Boolean)));
  const refCount = [reference, viewReferences?.left, viewReferences?.right, viewReferences?.behavior, applicationReference]
    .filter(r => r?.exists).length;

  return (
    <article className={"material-card" + (open ? " open" : "")}>
      <button className="material-head" type="button" onClick={() => setOpen(value => !value)}>
        <div className={"material-mini mat-" + material.tex}><span className={"fabric-overlay " + material.tex}></span></div>
        <div>
          <strong>{material.name_pl}</strong>
          <span>{material.prop_pl} · {material.finish_pl} · {refCount ? `${refCount} zdjęć referencyjnych` : "bez zdjęć — tylko opis"}</span>
        </div>
        <code>{material.id}</code>
        <span className="material-caret">{open ? "−" : "+"}</span>
      </button>

      {open && (
        <div className="material-body">
          <div className="reference-stack">
            <AuthedReference
              title="Wzorzec faktury"
              description="Makro lub płaska próbka. Model kopiuje z niej mikrosplot i skalę, bez koloru i geometrii. Zdjęcia są zapisywane jako JPEG do 2048 px."
              alt={`Wzorzec faktury ${material.name_pl}`}
              reference={reference} pendingFile={pendingFile} deleted={deleted}
              onFile={onFile} onDelete={onDeleteReference}
            />
            <AuthedReference
              title="Widok pod kątem — lewa strona"
              description="Płaska próbka oglądana z lewej. Razem z prawym kątem pokazuje kierunkowy połysk i relief włókien."
              alt={`Lewy kąt ${material.name_pl}`}
              reference={viewReferences?.left} pendingFile={pendingViewFiles?.left}
              deleted={deletedViewKeys?.has(`${material.id}:left`)}
              onFile={file => onViewFile("left", file)} onDelete={() => onDeleteViewReference("left")}
            />
            <AuthedReference
              title="Widok pod kątem — prawa strona"
              description="Płaska próbka oglądana z prawej. Model porównuje oba kąty zamiast kopiować jedno ustawienie światła."
              alt={`Prawy kąt ${material.name_pl}`}
              reference={viewReferences?.right} pendingFile={pendingViewFiles?.right}
              deleted={deletedViewKeys?.has(`${material.id}:right`)}
              onFile={file => onViewFile("right", file)} onDelete={() => onDeleteViewReference("right")}
            />
            <AuthedReference
              title="Zagięcie / zachowanie materiału"
              description="Próbka na krzywiźnie lub zagnieceniu. Pokazuje zmianę włosa, mikrocienie i zachowanie skali splotu na załamaniu."
              alt={`Zagięcie ${material.name_pl}`}
              reference={viewReferences?.behavior} pendingFile={pendingViewFiles?.behavior}
              deleted={deletedViewKeys?.has(`${material.id}:behavior`)}
              onFile={file => onViewFile("behavior", file)} onDelete={() => onDeleteViewReference("behavior")}
            />
            <AuthedReference
              title="Materiał na meblu / konkurencja"
              description="Zdjęcie pełnego mebla pokazujące wygląd tkaniny z dystansu. Model nie może kopiować bryły, szwów, pikowania, wnętrza ani stylizacji."
              alt={`Materiał ${material.name_pl} na meblu`}
              reference={applicationReference} pendingFile={pendingApplicationFile} deleted={applicationDeleted}
              onFile={onApplicationFile} onDelete={onDeleteApplicationReference}
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
                {texOptions.map(value => <option key={value}>{value}</option>)}
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

function CollectionCard({ collection, materials, groups, onChange, onDelete }) {
  const patch = values => onChange({ ...collection, ...values });
  const codes = collection.codes || [];
  const patchCode = (index, values) => patch({ codes: codes.map((c, i) => (i === index ? { ...c, ...values } : c)) });
  const removeCode = index => patch({ codes: codes.filter((_, i) => i !== index) });
  const addCode = () => patch({
    codes: [...codes, { code: "", hex: "#8A8A8A", name_pl: "", prompt_en: "", hex_verified: true, group: "" }],
  });
  const materialName = materials.find(m => m.id === collection.material)?.name_pl || collection.material;

  return (
    <article className="collection-card">
      <div className="collection-head">
        <div>
          <h3>{collection.name_pl || "Nowa kolekcja"}</h3>
          <small>{collection.id || "bez-id"} · {materialName || "bez tkaniny"} · {codes.length} {codes.length === 1 ? "kod" : "kodów"}</small>
        </div>
        <button className="icon-delete" type="button" title="Usuń kolekcję" onClick={onDelete}>×</button>
      </div>
      <div className="admin-grid">
        <Field label="ID" hint="Małe litery, bez spacji. Kolor kodu dostaje ID „<kolekcja>-<kod>”.">
          <input value={collection.id} onChange={event => patch({ id: event.target.value.toLowerCase().replace(/\s+/g, "-") })} />
        </Field>
        <Field label="Nazwa kolekcji">
          <input value={collection.name_pl} onChange={event => patch({ name_pl: event.target.value })} />
        </Field>
        <Field label="Tkanina" hint="Wybór koloru z tej kolekcji ustawia ten materiał w konfiguratorze.">
          <select value={collection.material} onChange={event => patch({ material: event.target.value })}>
            {materials.map(m => <option key={m.id} value={m.id}>{m.name_pl} ({m.id})</option>)}
          </select>
        </Field>
        <Field label="Opis / notatka">
          <input value={collection.description_pl || ""} onChange={event => patch({ description_pl: event.target.value })} />
        </Field>
      </div>

      <table className="code-table">
        <thead>
          <tr><th>Kod</th><th>HEX</th><th>Nazwa</th><th>Opis dla modelu (EN)</th><th>Grupa</th><th></th></tr>
        </thead>
        <tbody>
          {codes.map((entry, index) => (
            <tr key={index}>
              <td style={{ width: 70 }}>
                <input type="text" className="mono" value={entry.code} placeholder="27"
                  onChange={event => patchCode(index, { code: event.target.value.trim() })} />
              </td>
              <td style={{ width: 210 }}>
                <div className="code-hex">
                  <input type="color" value={/^#[0-9A-Fa-f]{6}$/.test(entry.hex) ? entry.hex : "#888888"}
                    onChange={event => patchCode(index, { hex: event.target.value.toUpperCase(), hex_verified: true })} />
                  <input type="text" className="mono" value={entry.hex}
                    onChange={event => patchCode(index, { hex: event.target.value.toUpperCase(), hex_verified: true })} />
                  <label className="code-approx" title="Odznaczone = HEX zmierzony z próbki. Zaznaczone = przybliżenie z grupy TreeTale.">
                    <input type="checkbox" checked={entry.hex_verified === false}
                      onChange={event => patchCode(index, { hex_verified: !event.target.checked })} />
                    ≈
                  </label>
                </div>
              </td>
              <td style={{ width: 150 }}>
                <input type="text" value={entry.name_pl || ""} placeholder={`${collection.name_pl || ""} ${entry.code}`.trim()}
                  onChange={event => patchCode(index, { name_pl: event.target.value })} />
              </td>
              <td>
                <input type="text" value={entry.prompt_en || ""} placeholder="np. very deep dark green, almost black bottle green (hex #122D24)"
                  onChange={event => patchCode(index, { prompt_en: event.target.value })} />
              </td>
              <td style={{ width: 120 }}>
                <select value={entry.group || ""} onChange={event => patchCode(index, { group: event.target.value })}
                  style={{ width: "100%", border: "1px solid var(--line-2)", borderRadius: 7, padding: "5px 6px", fontSize: 11, background: "#fffefb" }}>
                  <option value="">—</option>
                  {groups.map(g => <option key={g.id} value={g.id}>{g.name_pl}</option>)}
                </select>
              </td>
              <td className="actions"><button className="icon-delete" type="button" title="Usuń kod" onClick={() => removeCode(index)}>×</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ marginTop: 10 }}>
        <button className="admin-button secondary" type="button" onClick={addCode}>+ Dodaj kod</button>
      </div>
    </article>
  );
}

function TokenGate({ status, onSubmit }) {
  const [value, setValue] = useState("");
  const isDocker = status?.status === 403;
  return (
    <div className="app-frame admin-frame">
      <NanoTopbar active="admin" hideApiKey adminLabel="wymaga tokenu" />
      <main className="admin-gate">
        <h1>Panel Katalog</h1>
        {isDocker ? (
          <p>{status.detail} Dodaj <code>ADMIN_TOKEN=…</code> do pliku <code>.env</code> obok <code>docker-compose.yml</code>, uruchom ponownie kontener i wpisz ten sam token poniżej.</p>
        ) : (
          <p>Ta instancja wymaga tokenu administratora. Wpisz wartość <code>ADMIN_TOKEN</code> ustawioną na serwerze. Token zostaje w tej przeglądarce.</p>
        )}
        <form onSubmit={event => { event.preventDefault(); onSubmit(value.trim()); }}>
          <input type="password" autoFocus placeholder="token administratora" value={value} onChange={event => setValue(event.target.value)} />
          <button className="admin-button primary" type="submit" disabled={!value.trim()}>Otwórz</button>
        </form>
        {status?.detail && !isDocker && status.status === 401 && readToken() && (
          <div className="gate-error">Token został odrzucony. Sprawdź wartość i spróbuj ponownie.</div>
        )}
      </main>
    </div>
  );
}

function RepoPanel({ git, buildStatus, busy, onRetry }) {
  if (!git) return null;
  const pending = git.pending;
  let pill;
  if (!git.enabled) pill = <span className="repo-pill off">bez repozytorium</span>;
  else if (pending) pill = <span className="repo-pill err">czeka na wysyłkę</span>;
  else if (buildStatus?.state === "building" || buildStatus?.state === "queued") pill = <span className="repo-pill warn">buduje obraz</span>;
  else if (buildStatus?.state === "failed") pill = <span className="repo-pill err">testy CI padły</span>;
  else pill = <span className="repo-pill ok">w repozytorium</span>;

  const last = git.last_push;
  return (
    <section className="repo-panel">
      <div>
        <div className="repo-title">Repozytorium {pill}</div>
        <div className="repo-body">
          {!git.enabled && (
            <>Zmiany działają tylko na tej instancji. Żeby trafiały do <code>{git.repo}</code> i do wszystkich instalacji, ustaw <code>CATALOG_GIT_TOKEN</code> w <code>.env</code>.
              {pending && <> Od {new Date((pending.since || 0) * 1000).toLocaleString("pl-PL")} są edycje lokalne; aktualizacja obrazu ich nie nadpisze.</>}</>
          )}
          {git.enabled && pending && (
            <>Ostatni zapis nie dotarł do <code>{git.repo}</code>: {pending.message}{pending.detail ? <> (<span style={{ fontFamily: "Geist Mono", fontSize: 10 }}>{pending.detail}</span>)</> : null}. Edycje działają lokalnie.</>
          )}
          {git.enabled && !pending && last && (
            <>Ostatni commit <a href={last.url} target="_blank" rel="noreferrer">{String(last.sha).slice(0, 10)}</a> na <code>{git.branch}</code>, {new Date(last.at * 1000).toLocaleString("pl-PL")}
              {last.noop ? " (bez zmian względem repozytorium)" : ` (${(last.files_changed || []).length} plików)`}.
              {buildStatus?.state === "building" && " CI buduje obraz — inne instancje dostaną go po Watchtowerze (5–10 min)."}
              {buildStatus?.state === "success" && " Obraz zbudowany; Watchtower rozprowadzi go w ciągu kilku minut."}
              {buildStatus?.state === "failed" && buildStatus.runs?.[0]?.url && <> Testy CI nie przeszły — <a href={buildStatus.runs[0].url} target="_blank" rel="noreferrer">zobacz log</a>; obraz nie został opublikowany.</>}
            </>
          )}
          {git.enabled && !pending && !last && <>Skonfigurowane dla <code>{git.repo}</code> ({git.branch}). Pierwszy zapis utworzy commit.</>}
          {git.build_sha && <> Obraz: <code>{String(git.build_sha).slice(0, 10)}</code>.</>}
        </div>
      </div>
      <div className="repo-actions">
        {git.enabled && pending && (
          <button className="admin-button secondary" type="button" disabled={busy} onClick={onRetry}>Wyślij ponownie</button>
        )}
        {git.url && <a className="admin-button secondary" href={git.url} target="_blank" rel="noreferrer">GitHub ↗</a>}
      </div>
    </section>
  );
}

function AdminApp() {
  const [payload, setPayload] = useState(null);
  const [catalog, setCatalog] = useState(null);
  const [baseline, setBaseline] = useState("");
  const [tab, setTab] = useState("materials");
  const [gate, setGate] = useState(null);           // { status, detail } while locked out
  const [pendingRefs, setPendingRefs] = useState({});
  const [deletedRefs, setDeletedRefs] = useState(new Set());
  const [pendingApplicationRefs, setPendingApplicationRefs] = useState({});
  const [deletedApplicationRefs, setDeletedApplicationRefs] = useState(new Set());
  const [pendingViewRefs, setPendingViewRefs] = useState({});
  const [deletedViewRefs, setDeletedViewRefs] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState({ type: "", text: "" });
  const [buildState, setBuildState] = useState(null);
  const [buildStatus, setBuildStatus] = useState(null);
  const statusTimer = useRef(null);
  const ciTimer = useRef(null);

  const load = async () => {
    try {
      const data = await adminFetch("/api/admin/catalog");
      const next = clone(data.catalog);
      if (!Array.isArray(next.collections)) next.collections = [];
      setGate(null);
      setPayload(data);
      setCatalog(next);
      setBaseline(JSON.stringify(next));
      setBuildState(data.build);
    } catch (error) {
      if (error instanceof AuthError) { setGate({ status: error.status, detail: error.detail }); return; }
      setStatus({ type: "error", text: errorMessage(error, "Nie udało się wczytać katalogu.") });
    }
  };
  useEffect(() => { load(); }, []);

  // Poll the CI state of the last push while it is still running.
  const watchBuild = (sha) => {
    clearInterval(ciTimer.current);
    if (!sha) return;
    const tick = async () => {
      try {
        const next = await adminFetch(`/api/admin/build-status?sha=${encodeURIComponent(sha)}`);
        setBuildStatus(next);
        if (next.state === "success" || next.state === "failed" || next.state === "unknown") clearInterval(ciTimer.current);
      } catch { clearInterval(ciTimer.current); }
    };
    tick();
    ciTimer.current = setInterval(tick, 30000);
  };
  useEffect(() => {
    const last = payload?.git?.last_push;
    if (last?.sha && !last.noop && Date.now() / 1000 - (last.at || 0) < 3600) watchBuild(last.sha);
    return () => clearInterval(ciTimer.current);
    // eslint-disable-next-line
  }, [payload?.git?.last_push?.sha]);

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
    ...current, materials: current.materials.map((value, i) => (i === index ? item : value)),
  }));
  const updateColor = (index, item) => setCatalog(current => ({
    ...current, colors: current.colors.map((value, i) => (i === index ? item : value)),
  }));
  const updateCollection = (index, item) => setCatalog(current => ({
    ...current, collections: current.collections.map((value, i) => (i === index ? item : value)),
  }));
  const setReference = (id, file) => {
    if (!file) return;
    setPendingRefs(current => ({ ...current, [id]: file }));
    setDeletedRefs(current => { const next = new Set(current); next.delete(id); return next; });
  };
  const deleteReference = id => {
    setPendingRefs(current => { const next = { ...current }; delete next[id]; return next; });
    setDeletedRefs(current => new Set(current).add(id));
  };
  const setApplicationReference = (id, file) => {
    if (!file) return;
    setPendingApplicationRefs(current => ({ ...current, [id]: file }));
    setDeletedApplicationRefs(current => { const next = new Set(current); next.delete(id); return next; });
  };
  const deleteApplicationReference = id => {
    setPendingApplicationRefs(current => { const next = { ...current }; delete next[id]; return next; });
    setDeletedApplicationRefs(current => new Set(current).add(id));
  };
  const setViewReference = (id, role, file) => {
    if (!file) return;
    const key = `${id}:${role}`;
    setPendingViewRefs(current => ({ ...current, [key]: file }));
    setDeletedViewRefs(current => { const next = new Set(current); next.delete(key); return next; });
  };
  const deleteViewReference = (id, role) => {
    const key = `${id}:${role}`;
    setPendingViewRefs(current => { const next = { ...current }; delete next[key]; return next; });
    setDeletedViewRefs(current => new Set(current).add(key));
  };
  const addColor = () => setCatalog(current => ({
    ...current,
    colors: [...current.colors, {
      id: `kolor-${current.colors.length + 1}`, name_pl: "nowy kolor", hex: "#C8C3BA", fabric: true, covers: "",
      prompt_en: "neutral upholstery colour (hex #C8C3BA)",
    }],
  }));
  const addCollection = () => setCatalog(current => ({
    ...current,
    collections: [...(current.collections || []), {
      id: `kolekcja-${(current.collections || []).length + 1}`, name_pl: "Nowa kolekcja",
      material: current.materials[0]?.id || "", description_pl: "", codes: [],
    }],
  }));

  const startStatusPolling = () => {
    clearInterval(statusTimer.current);
    statusTimer.current = setInterval(async () => {
      try { setBuildState(await adminFetch("/api/admin/status")); } catch {}
    }, 700);
  };

  const applyResponse = (data) => {
    const next = clone(data.catalog);
    if (!Array.isArray(next.collections)) next.collections = [];
    setPayload(data);
    setCatalog(next);
    setBaseline(JSON.stringify(next));
    setPendingRefs({}); setDeletedRefs(new Set());
    setPendingApplicationRefs({}); setDeletedApplicationRefs(new Set());
    setPendingViewRefs({}); setDeletedViewRefs(new Set());
    setBuildState(data.build);
  };

  const save = async () => {
    if (!dirty || busy) return;
    setBusy(true);
    setStatus({ type: "working", text: "Sprawdzam dane…" });
    startStatusPolling();
    try {
      const body = new FormData();
      body.append("catalog_json", JSON.stringify(catalog));
      Object.entries(pendingRefs).forEach(([id, file]) => { body.append("reference_ids", id); body.append("reference_files", file, file.name); });
      body.append("delete_reference_ids_json", JSON.stringify([...deletedRefs]));
      Object.entries(pendingApplicationRefs).forEach(([id, file]) => { body.append("application_reference_ids", id); body.append("application_reference_files", file, file.name); });
      body.append("delete_application_reference_ids_json", JSON.stringify([...deletedApplicationRefs]));
      Object.entries(pendingViewRefs).forEach(([key, file]) => { body.append("view_reference_keys", key); body.append("view_reference_files", file, file.name); });
      body.append("delete_view_reference_keys_json", JSON.stringify([...deletedViewRefs]));
      const data = await adminFetch("/api/admin/catalog", { method: "POST", body });
      applyResponse(data);
      const git = data.git || {};
      if (git.pushed) {
        setStatus({ type: "success", text: `Zapisano. Commit ${String(git.sha).slice(0, 10)} trafił do repozytorium, CI buduje obraz. Backup: ${data.backup}.` });
        if (!git.noop) watchBuild(git.sha);
      } else if (git.enabled) {
        setStatus({ type: "error", text: `Zapisano lokalnie, ale wysyłka do repozytorium nie powiodła się: ${git.error || "błąd"}. Możesz ponowić z panelu Repozytorium.` });
      } else {
        setStatus({ type: "success", text: `Zapisano i przeładowano katalog na tej instancji (bez wysyłki do repozytorium). Backup: ${data.backup}.` });
      }
    } catch (error) {
      if (error instanceof AuthError) { setGate({ status: error.status, detail: error.detail }); return; }
      setStatus({ type: "error", text: errorMessage(error) });
    } finally {
      clearInterval(statusTimer.current);
      setBusy(false);
    }
  };

  const retryPush = async () => {
    if (busy) return;
    setBusy(true);
    setStatus({ type: "working", text: "Wysyłam katalog do repozytorium…" });
    try {
      const data = await adminFetch("/api/admin/retry-push", { method: "POST" });
      setBuildState(data.build);
      setPayload(current => ({ ...current, git: { ...(current?.git || {}), pending: data.git.pending, last_push: data.git.pushed ? data.git : current?.git?.last_push } }));
      if (data.git.pushed) { setStatus({ type: "success", text: `Wysłano. Commit ${String(data.git.sha).slice(0, 10)}.` }); if (!data.git.noop) watchBuild(data.git.sha); }
      else setStatus({ type: "error", text: data.git.error || "Wysyłka nie powiodła się." });
    } catch (error) {
      if (error instanceof AuthError) { setGate({ status: error.status, detail: error.detail }); return; }
      setStatus({ type: "error", text: errorMessage(error) });
    } finally {
      setBusy(false);
    }
  };

  if (gate) {
    return <TokenGate status={gate} onSubmit={token => { storeToken(token); setGate(null); load(); }} />;
  }

  if (!catalog) {
    return (
      <div className="app-frame">
        <NanoTopbar active="admin" hideApiKey adminLabel={readToken() ? "token" : "tylko lokalnie"} />
        <main className="admin-loading">{status.text || "Ładuję katalog…"}</main>
      </div>
    );
  }

  const collections = catalog.collections || [];
  const gitInfo = payload?.git;

  return (
    <div className="app-frame admin-frame">
      <NanoTopbar active="admin" hideApiKey adminLabel={readToken() ? "token administratora" : "tylko lokalnie"} />
      <main className="admin-shell">
        <header className="admin-hero">
          <div>
            <span className="admin-eyebrow">ŹRÓDŁO PRAWDY · CATALOG.JSON</span>
            <h1>Materiały, kolekcje i kolory</h1>
            <p>Zmieniasz dane, które widzi konfigurator i model. Zapis sprawdza dane, przeładowuje katalog na tej instancji{gitInfo?.enabled ? " i wysyła commit do repozytorium, z którego CI buduje nowy obraz dla wszystkich" : ""}.</p>
          </div>
          <div className="admin-health">
            <span className={"health-dot " + (buildState?.state || "idle")}></span>
            <div><strong>{buildState?.message || "Gotowy"}</strong><small>{catalog.materials.length} tkanin · {collections.length} kolekcji · {catalog.colors.length} kolorów</small></div>
          </div>
        </header>

        <RepoPanel git={gitInfo} buildStatus={buildStatus} busy={busy} onRetry={retryPush} />

        <div className="admin-tabs">
          <button className={tab === "materials" ? "on" : ""} onClick={() => setTab("materials")}>Tkaniny <span>{catalog.materials.length}</span></button>
          <button className={tab === "collections" ? "on" : ""} onClick={() => setTab("collections")}>Kolekcje <span>{collections.length}</span></button>
          <button className={tab === "colors" ? "on" : ""} onClick={() => setTab("colors")}>Kolory grupowe <span>{catalog.colors.length}</span></button>
        </div>

        {tab === "materials" && (
          <section className="admin-list">
            <div className="section-intro">
              <div><h2>Tkaniny</h2><p>Opisy i zdjęcia wzorcowe są razem. Lista typów tkanin jest zablokowana przez schemat generatora; nowy typ to zmiana w kodzie.</p></div>
            </div>
            {catalog.materials.map((material, index) => (
              <MaterialCard
                key={material.id}
                material={material}
                knownTex={payload.known_tex}
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
        )}

        {tab === "collections" && (
          <section className="admin-list">
            <div className="section-intro">
              <div><h2>Kolekcje tkanin</h2><p>Kolekcja (np. Velutto) ma tkaninę i listę kodów z dokładnym HEX-em. Każdy kod jest osobnym kolorem w konfiguratorze i zapisuje się w metadanych renderu. Znak „≈” oznacza HEX przybliżony z grupy TreeTale — wpisz zmierzony z próbki.</p></div>
              <button className="admin-button secondary" type="button" onClick={addCollection}>+ Dodaj kolekcję</button>
            </div>
            {collections.length === 0 && <div className="admin-empty">Brak kolekcji. Dodaj pierwszą, np. Velutto z tkaniną welur.</div>}
            {collections.map((collection, index) => (
              <CollectionCard
                key={`${collection.id}-${index}`}
                collection={collection}
                materials={catalog.materials}
                groups={catalog.colors}
                onChange={item => updateCollection(index, item)}
                onDelete={() => setCatalog(current => ({ ...current, collections: current.collections.filter((_, i) => i !== index) }))}
              />
            ))}
          </section>
        )}

        {tab === "colors" && (
          <section className="admin-list">
            <div className="section-intro">
              <div><h2>Kolory grupowe</h2><p>Uniwersalne grupy kolorów TreeTale dla tkanin bez własnych kodów. HEX kotwiczy odcień, a angielski opis doprecyzowuje podton.</p></div>
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
