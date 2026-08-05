import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  HardDrive,
  RefreshCw,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import "./commissioning.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";

async function json(path: string, token: string, options: RequestInit = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${token}`, ...options.headers },
  });
  if (!response.ok)
    throw new Error(
      (
        await response.json().catch(() => ({ detail: response.statusText }))
      ).detail,
    );
  return response.json();
}

export function CommissioningCenter({ token }: { token: string }) {
  const [report, setReport] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const load = async () => {
    setError("");
    try {
      setReport(await json("/commissioning", token));
    } catch (e: any) {
      setError(e.message);
    }
  };
  useEffect(() => {
    void load();
  }, [token]);
  async function backup() {
    setBusy(true);
    setError("");
    try {
      const item = await json("/maintenance/backup", token, { method: "POST" });
      setMessage(`Backup verificato: ${item.file}`);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function testAll() {
    setBusy(true);
    setError("");
    try {
      const result = await json("/commissioning/test-all", token, {
        method: "POST",
      });
      setMessage(
        `Collaudo completato: ${result.results.filter((item: any) => item.status === "online").length}/${result.results.length} connessioni online`,
      );
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function download(file: string) {
    setError("");
    try {
      const response = await fetch(
        `${apiBase}/maintenance/backups/${encodeURIComponent(file)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error("Download non riuscito");
      const blob = await response.blob(),
        url = URL.createObjectURL(blob),
        anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = file;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  }
  if (!report)
    return (
      <div className="commission-loading">
        <Wrench />
        Preparazione checklist di collaudo…
      </div>
    );
  return (
    <div className="commission">
      <header className="commission-head">
        <div>
          <p>EDGE SITE ACCEPTANCE TEST</p>
          <h1>Commissioning impianto</h1>
          <span>
            Checklist tecnica basata sullo stato reale dell’Edge. La consegna è
            consentita solo senza blocchi.
          </span>
        </div>
        <div>
          <button onClick={() => void load()}>
            <RefreshCw />
            Aggiorna
          </button>
          <button disabled={busy} onClick={() => void testAll()}>
            <Wrench />
            Test impianto
          </button>
          <button
            className="commission-primary"
            disabled={busy}
            onClick={() => void backup()}
          >
            <HardDrive />
            {busy ? "Creazione…" : "Crea backup"}
          </button>
        </div>
      </header>
      {error && (
        <div className="commission-error">
          <AlertTriangle />
          {error}
        </div>
      )}
      {message && (
        <div className="commission-message">
          <CheckCircle2 />
          {message}
        </div>
      )}
      <section
        className={`commission-verdict ${report.ready ? "ready" : "blocked"}`}
      >
        <div className="commission-score">
          <strong>{report.score}</strong>
          <span>/100</span>
        </div>
        <div>
          {report.ready ? <ShieldCheck /> : <AlertTriangle />}
          <span>
            <b>
              {report.ready
                ? "Edge pronto alla consegna"
                : "Commissioning non completato"}
            </b>
            <small>
              {report.ready
                ? "Tutti i controlli bloccanti risultano superati."
                : `${report.blocking_failures} controlli bloccanti richiedono intervento.`}
            </small>
          </span>
        </div>
        <dl>
          <div>
            <dt>Release</dt>
            <dd>{report.release}</dd>
          </div>
          <div>
            <dt>Ambiente</dt>
            <dd>{report.environment}</dd>
          </div>
          <div>
            <dt>Retention</dt>
            <dd>{report.retention_days} giorni</dd>
          </div>
          <div>
            <dt>Disco libero</dt>
            <dd>{report.storage.free_percent}%</dd>
          </div>
        </dl>
      </section>
      <section className="commission-list">
        <header>
          <div>
            <p>PROTOCOLLO DI VERIFICA</p>
            <h2>Controlli di accettazione</h2>
          </div>
          <span>{report.checks.length} controlli</span>
        </header>
        {report.checks.map((item: any) => (
          <article key={item.id} className={item.status}>
            <div className="commission-icon">
              {item.status === "pass" ? (
                <CheckCircle2 />
              ) : item.status === "warn" ? (
                <AlertTriangle />
              ) : (
                <XCircle />
              )}
            </div>
            <div>
              <span>{item.blocking ? "BLOCCANTE" : "RACCOMANDATO"}</span>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
              <small>{item.action}</small>
            </div>
            <em>
              {item.status === "pass"
                ? "Superato"
                : item.status === "warn"
                  ? "Da presidiare"
                  : "Non superato"}
            </em>
            {item.id === "backup" && report.backups?.[0] && (
              <button
                title="Scarica ultimo backup"
                onClick={() => void download(report.backups[0].file)}
              >
                <Download />
              </button>
            )}
          </article>
        ))}
      </section>
      <footer className="commission-foot">
        <ShieldCheck />
        <span>
          Il report attesta controlli software e configurativi, non sostituisce
          verbali elettrici, verifiche metrologiche o collaudi previsti dal
          contratto.
        </span>
      </footer>
    </div>
  );
}
