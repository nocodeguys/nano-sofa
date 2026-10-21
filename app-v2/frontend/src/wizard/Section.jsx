import React from "react";

/* generic section wrapper */
export function Section({ num, title, summary, help, children }) {
  return (
    <section className="section" id={`section-${num}`}>
      <div className="sec-head">
        <div className="num">{num}</div>
        <div className="title serif">{title}</div>
        {summary && <div className="summary">{summary}</div>}
      </div>
      {help && <p className="sec-help">{help}</p>}
      <div className="sec-body">{children}</div>
    </section>
  );
}

export function AdvancedSection({ title, summary, help, children }) {
  return (
    <details className="advanced-section">
      <summary className="sec-head">
        <div className="num">+</div>
        <div className="title serif">{title}</div>
        {summary && <div className="summary">{summary}</div>}
      </summary>
      <div className="advanced-body">
        {help && <p className="sec-help">{help}</p>}
        <div className="sec-body">{children}</div>
      </div>
    </details>
  );
}
