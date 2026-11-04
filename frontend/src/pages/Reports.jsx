import { useState } from "react";
import { download, errMsg } from "../services/api";
import { Btn, Card, ErrorBox, PageHeader } from "../components/ui";

const SECTIONS = [["summary", "Monitoring summary"], ["carbon", "Carbon by workload"], ["models", "Model performance"], ["recommendations", "Recommendations"], ["comparison", "Before / after"], ["methodology", "Methodology & assumptions"], ["full", "Everything (one CSV)"]];

export default function Reports() {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState(null);
  const go = async (format, section) => {
    setBusy(`${format}-${section}`); setErr(null);
    try { await download("/reports/generate", { format, section }, `greencloud_${section}.${format}`); } catch (e) { setErr(errMsg(e)); } finally { setBusy(""); }
  };
  return (
    <>
      <PageHeader title="Reports" subtitle="Downloadable CSV and PDF. Methodology and assumptions are always included." />
      {err && <div className="mb-3"><ErrorBox error={err} /></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="PDF report">
          <p className="mb-3 text-sm text-slate-600">Monitoring summary, carbon footprint, model performance, recommendations, before-and-after comparison, methodology and assumptions.</p>
          <Btn onClick={() => go("pdf", "full")} disabled={!!busy}>{busy === "pdf-full" ? "Generating…" : "Download PDF"}</Btn>
        </Card>
        <Card title="CSV sections">
          <div className="flex flex-wrap gap-2">{SECTIONS.map(([k, l]) => <Btn key={k} kind="secondary" onClick={() => go("csv", k)} disabled={!!busy}>{busy === `csv-${k}` ? "…" : l}</Btn>)}</div>
        </Card>
      </div>
    </>
  );
}
