import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import "./styles-v2.css";
import "./experiments.css";
import { NanoTopbar } from "./header.jsx";

const short = value => value ? value.slice(0, 10) : "—";
const modelName = value => value?.includes("3-pro") ? "Pro" : value?.includes("3.1-flash") ? "Flash" : value || "—";
const dateLabel = value => value ? new Intl.DateTimeFormat("pl-PL", { dateStyle: "short", timeStyle: "short" }).format(new Date(value * 1000)) : "—";

function RunImage({ run, label }) {
  return (
    <article className="ab-result">
      <div className="ab-result-head">
        <span className="ab-letter">{label}</span>
        <div><strong>{modelName(run.model)}</strong><small>{run.resolution || "—"} · {dateLabel(run.created_at)}</small></div>
        <span className={run.tracked ? "trace-chip good" : "trace-chip"}>{run.tracked ? "pełny zapis" : "starszy wynik"}</span>
      </div>
      <div className="ab-hero-image">{run.image_url ? <img src={run.image_url} alt={`Wariant ${label}`} /> : <span>brak obrazu</span>}</div>
      <div className="ab-run-meta">
        <span><b>{run.elapsed_ms ? `${(run.elapsed_ms / 1000).toFixed(1)} s` : "—"}</b><small>czas</small></span>
        <span><b>{run.actual_cost != null ? `$${Number(run.actual_cost).toFixed(3)}` : "—"}</b><small>koszt</small></span>
        <span><b>{run.references?.length || "—"}</b><small>referencje</small></span>
      </div>
      {run.prompt && <details><summary>Pokaż rzeczywisty prompt</summary><pre>{run.prompt}</pre></details>}
    </article>
  );
}

function ComparisonFact({ label, a, b, comparable = true }) {
  const same = comparable && a && b && a === b;
  return (
    <div className="compare-fact">
      <span>{label}</span>
      <b className={same ? "same" : "different"}>{!comparable ? "brak danych" : same ? "identyczne" : "różne"}</b>
      <small>{short(a)} ↔ {short(b)}</small>
    </div>
  );
}

function RunCard({ run, selected, onToggle }) {
  return (
    <button type="button" className={`run-card${selected ? " selected" : ""}`} onClick={onToggle}>
      <div className="run-thumb">{run.image_url ? <img src={run.image_url} alt="" loading="lazy" /> : <span>bez obrazu</span>}<i>{selected ? "✓" : "+"}</i></div>
      <div className="run-copy">
        <strong>{modelName(run.model)} <em>{run.resolution}</em></strong>
        <span>{run.material || run.prompt_summary || "Generacja obrazu"}</span>
        <small>{dateLabel(run.created_at)} · {run.tracked ? "pełny zapis" : "ograniczone dane"}</small>
      </div>
    </button>
  );
}

function ExperimentsApp() {
  const [payload, setPayload] = useState(null);
  const [selected, setSelected] = useState([]);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    setError("");
    try {
      const response = await fetch("/api/experiments?limit=200", { cache: "no-store" });
      if (!response.ok) throw new Error(`Błąd serwera (${response.status})`);
      setPayload(await response.json());
    } catch (err) { setError(err.message || "Nie udało się wczytać eksperymentów."); }
  };
  useEffect(() => { load(); }, []);

  const items = useMemo(() => (payload?.items || []).filter(run => {
    if (filter === "tracked" && !run.tracked) return false;
    if (filter === "pro" && !run.model?.includes("pro")) return false;
    if (filter === "flash" && !run.model?.includes("flash")) return false;
    const haystack = `${run.model} ${run.material} ${run.color} ${run.prompt_summary} ${run.generation_id}`.toLowerCase();
    return haystack.includes(query.trim().toLowerCase());
  }), [payload, filter, query]);

  const chosen = selected.map(id => payload?.items.find(item => item.generation_id === id)).filter(Boolean);
  const toggle = id => setSelected(current => current.includes(id) ? current.filter(value => value !== id) : current.length < 2 ? [...current, id] : [current[1], id]);
  const refsSignature = run => run.references?.map(ref => `${ref.role}:${ref.sha256}`).join("|") || null;
  const controlled = chosen.length === 2 && chosen.every(run => run.tracked);

  return (
    <div className="experiments-app">
      <NanoTopbar active="experiments" hideApiKey />
      <main className="experiments-main">
        <section className="experiments-intro">
          <div><span className="eyebrow">laboratorium generacji</span><h1>Eksperymenty A/B</h1><p>Wybierz dwa wyniki. Sprawdzimy, co naprawdę zmieniło się pomiędzy generacjami — zamiast zgadywać na podstawie samego obrazu.</p></div>
          <div className="experiment-rule"><b>Najlepszy test</b><span>jedna zmienna naraz</span><span>minimum 3 powtórzenia</span><span>ten sam produkt i referencje</span></div>
        </section>

        {chosen.length === 2 ? (
          <section className="comparison-panel">
            <div className="comparison-title"><div><span className="eyebrow">aktywne porównanie</span><h2>A kontra B</h2></div><button onClick={() => setSelected([])}>Wyczyść wybór</button></div>
            <div className="comparison-images"><RunImage run={chosen[0]} label="A" /><RunImage run={chosen[1]} label="B" /></div>
            <div className="comparison-audit">
              <div className={`control-verdict ${controlled ? "ready" : "legacy"}`}><b>{controlled ? "Można ocenić kontrolowany test" : "Porównanie wizualne — niepełne dane"}</b><span>{controlled ? "Obie generacje mają zapis promptu i referencji." : "Co najmniej jeden wynik powstał przed włączeniem manifestów."}</span></div>
              <ComparisonFact label="Prompt" a={chosen[0].prompt_sha256} b={chosen[1].prompt_sha256} comparable={controlled} />
              <ComparisonFact label="Referencje" a={refsSignature(chosen[0])} b={refsSignature(chosen[1])} comparable={controlled} />
              <ComparisonFact label="Pełne wejście" a={chosen[0].setup_fingerprint} b={chosen[1].setup_fingerprint} comparable={controlled} />
              <ComparisonFact label="Model" a={chosen[0].model} b={chosen[1].model} />
            </div>
          </section>
        ) : (
          <section className="comparison-placeholder"><span>{chosen.length ? "1 / 2" : "0 / 2"}</span><div><b>Wybierz dwa rendery do porównania</b><small>Kliknij kafelki poniżej. Trzeci wybór zastąpi najstarszy.</small></div></section>
        )}

        <section className="runs-section">
          <div className="runs-toolbar">
            <div><span className="eyebrow">historia prób</span><h2>Wyniki generacji</h2></div>
            <div className="run-controls"><input placeholder="Szukaj…" value={query} onChange={e => setQuery(e.target.value)} /><select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Wszystkie</option><option value="tracked">Pełny zapis</option><option value="flash">Flash</option><option value="pro">Pro</option></select><button onClick={load}>Odśwież</button></div>
          </div>
          {error && <div className="experiment-error">{error}</div>}
          {!payload && !error ? <div className="experiment-empty">Wczytuję historię…</div> : items.length ? <div className="runs-grid">{items.map(run => <RunCard key={run.generation_id} run={run} selected={selected.includes(run.generation_id)} onToggle={() => toggle(run.generation_id)} />)}</div> : <div className="experiment-empty"><b>Brak wyników dla tego filtra</b><span>Nowe generacje pojawią się tutaj automatycznie.</span></div>}
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<ExperimentsApp />);
