// Parameter-docs page (/help). Joins Polish labels (NS_DATA) with the English
// prompt clauses from /api/param-docs by shared id — reusing the app's data
// layer so this page can't drift from the configurator.
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-mono/400.css";
import { NS_DATA } from "./data.jsx";

(async () => {
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const D = NS_DATA;
  const body = document.getElementById("doc-body");
  const toc = document.getElementById("toc");
  let groups;
  try {
    const r = await fetch("/api/param-docs");
    ({ groups } = await r.json());
  } catch (e) {
    body.innerHTML = '<div class="loading">Nie udało się wczytać opisów parametrów. Odśwież stronę.</div>';
    return;
  }
  body.innerHTML = "";
  groups.forEach(g => {
    const table = D[g.table] || [];
    const rows = table.map(item => {
      const clause = g.clauses[item.id];
      if (!clause) return "";
      const sw = item.hex ? `<span class="sw" style="background:${esc(item.hex)}"></span>` : "";
      return `<tr><td class="opt">${sw}${esc(item.name || item.id)}<span class="id">${esc(item.id)}</span></td>`
           + `<td class="clause">${esc(clause)}</td></tr>`;
    }).filter(Boolean).join("");
    if (!rows) return;
    const sec = document.createElement("section");
    sec.innerHTML = `<h2 id="g-${esc(g.key)}">${esc(g.title)}</h2>`
                  + `<div class="card"><table><tbody>${rows}</tbody></table></div>`;
    body.appendChild(sec);
    const a = document.createElement("a");
    a.href = `#g-${g.key}`; a.textContent = g.title;
    toc.appendChild(a);
  });
  // Add the matrix anchor to the TOC too.
  const m = document.createElement("a");
  m.href = "#matrix"; m.textContent = "Galeria (wkrótce)";
  toc.appendChild(m);
})();
