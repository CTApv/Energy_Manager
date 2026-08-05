import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  CheckCircle2,
  Download,
  Factory,
  Gauge,
  Leaf,
  RefreshCw,
  Save,
  Settings2,
  Sun,
  WalletCards,
  X,
} from "lucide-react";
import "./monitoring-studio.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";
const periods = [
  ["day", "Oggi"],
  ["week", "Settimana"],
  ["month", "Mese"],
  ["year", "Anno"],
];
const days = ["L", "M", "M", "G", "V", "S", "D"];
const number = (value: any, digits = 1) =>
  value === null || value === undefined
    ? "—"
    : Number(value).toLocaleString("it-IT", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });
const money = (value: any, currency = "EUR") =>
  value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat("it-IT", {
        style: "currency",
        currency,
        maximumFractionDigits: 2,
      }).format(Number(value));

async function json(path: string, token: string, options: RequestInit = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
  });
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => ({}))).detail ||
        "Servizio energetico non disponibile",
    );
  return response.json();
}

function SparkBars({ points }: { points: any[] }) {
  const max = Math.max(
    ...points.map((item) => Number(item.energy_kwh) || 0),
    1,
  );
  if (!points.length)
    return (
      <div className="monitor-empty">
        Nessun incremento energetico valido nel periodo.
      </div>
    );
  return (
    <div className="monitor-chart">
      <div className="monitor-bars">
        {points.map((item, index) => (
          <div
            key={item.time}
            className="monitor-bar-wrap"
            title={`${new Date(item.time).toLocaleString("it-IT")}: ${number(item.energy_kwh, 2)} kWh`}
          >
            <i
              style={{
                height: `${Math.max(3, (Number(item.energy_kwh) / max) * 100)}%`,
                animationDelay: `${Math.min(index * 30, 500)}ms`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="monitor-axis">
        <span>
          {new Date(points[0].time).toLocaleDateString("it-IT", {
            day: "2-digit",
            month: "short",
            hour: "2-digit",
          })}
        </span>
        <span>
          {new Date(points.at(-1).time).toLocaleDateString("it-IT", {
            day: "2-digit",
            month: "short",
            hour: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
}

function Kpi({
  icon: Icon,
  label,
  value,
  unit,
  tone = "green",
  note,
}: {
  icon: any;
  label: string;
  value: any;
  unit?: string;
  tone?: string;
  note: string;
}) {
  return (
    <article className={`monitor-kpi ${tone}`}>
      <span className="monitor-kpi-icon">
        <Icon />
      </span>
      <div>
        <p>{label}</p>
        <strong>
          {value} {unit && <small>{unit}</small>}
        </strong>
        <em>{note}</em>
      </div>
    </article>
  );
}

export function MonitoringStudio({ token }: { token: string }) {
  const [period, setPeriod] = useState("month"),
    [report, setReport] = useState<any>(null),
    [configuration, setConfiguration] = useState<any>(null),
    [draft, setDraft] = useState<any>(null),
    [settingsOpen, setSettingsOpen] = useState(false),
    [loading, setLoading] = useState(true),
    [saving, setSaving] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [nextReport, nextConfiguration] = await Promise.all([
        json(`/energy/report?period=${period}`, token),
        json("/energy/settings", token),
      ]);
      setReport(nextReport);
      setConfiguration(nextConfiguration);
      setDraft(nextConfiguration);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, [token, period]);
  const currency = report?.economics?.currency || "EUR",
    energy = report?.energy || {},
    power = report?.power || {},
    economics = report?.economics || {},
    budget = report?.budget || {},
    environment = report?.environment || {};
  const maxBreakdown = useMemo(
    () =>
      Math.max(
        ...(report?.breakdown || []).map(
          (item: any) => Number(item.energy_kwh) || 0,
        ),
        1,
      ),
    [report],
  );
  const qualityGood = energy.quality === "good" && power.coverage_percent >= 80;
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        ...draft,
        import_price_per_kwh: Number(draft.import_price_per_kwh),
        export_price_per_kwh: Number(draft.export_price_per_kwh),
        co2_kg_per_kwh: Number(draft.co2_kg_per_kwh),
        contracted_power_kw:
          draft.contracted_power_kw === ""
            ? null
            : Number(draft.contracted_power_kw),
        monthly_energy_budget_kwh:
          draft.monthly_energy_budget_kwh === ""
            ? null
            : Number(draft.monthly_energy_budget_kwh),
        monthly_cost_budget:
          draft.monthly_cost_budget === ""
            ? null
            : Number(draft.monthly_cost_budget),
      };
      await json("/energy/settings", token, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setSettingsOpen(false);
      setMessage("Parametri energetici salvati e report ricalcolato.");
      setTimeout(() => setMessage(""), 3500);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }
  async function download() {
    try {
      const response = await fetch(
        `${apiBase}/energy/report.csv?period=${period}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error("Export non disponibile");
      const url = URL.createObjectURL(await response.blob()),
        link = document.createElement("a");
      link.href = url;
      link.download = `energy-report-${period}-${new Date().toISOString().slice(0, 10)}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message);
    }
  }
  if (loading && !report)
    return (
      <div className="monitor-loading">
        <Gauge />
        Elaborazione bilancio energetico…
      </div>
    );
  return (
    <div className="monitor-studio">
      <header className="monitor-head">
        <div>
          <p>ENERGY INTELLIGENCE</p>
          <h1>Consumi e performance</h1>
          <span>
            {report?.source?.device_name
              ? `Bilancio autorevole da ${report.source.device_name}`
              : "Associa un contatore generale per attivare il bilancio"}
          </span>
        </div>
        <div className="monitor-actions">
          <button onClick={() => void load()}>
            <RefreshCw />
            Aggiorna
          </button>
          <button onClick={() => void download()}>
            <Download />
            CSV
          </button>
          <button
            className="monitor-primary"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings2 />
            Parametri
          </button>
        </div>
      </header>
      {error && (
        <div className="monitor-error">
          <AlertTriangle />
          {error}
        </div>
      )}
      {message && (
        <div className="monitor-success">
          <CheckCircle2 />
          {message}
        </div>
      )}
      <nav className="period-tabs">
        {periods.map(([id, label]) => (
          <button
            key={id}
            className={period === id ? "active" : ""}
            onClick={() => setPeriod(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      <section className="monitor-kpis">
        <Kpi
          icon={Gauge}
          label="Energia prelevata"
          value={number(energy.import_kwh)}
          unit="kWh"
          note={`${number(report?.comparison?.energy_change_percent)}% sul periodo precedente`}
        />
        <Kpi
          icon={WalletCards}
          label="Costo netto"
          value={money(economics.net_cost, currency)}
          note={`Proiezione mese ${money(economics.projected_month_cost, currency)}`}
          tone="blue"
        />
        <Kpi
          icon={BarChart3}
          label="Picco di potenza"
          value={number(power.peak_kw)}
          unit="kW"
          note={
            power.contracted_kw
              ? `${number((power.peak_kw / power.contracted_kw) * 100, 0)}% della potenza contrattuale`
              : "Potenza contrattuale da impostare"
          }
          tone={power.contract_exceeded ? "red" : "amber"}
        />
        <Kpi
          icon={Leaf}
          label="Emissioni associate"
          value={number(environment.co2_kg)}
          unit="kgCO₂e"
          note={`${number(environment.factor_kg_per_kwh, 3)} kgCO₂e/kWh`}
          tone="purple"
        />
      </section>
      <div className="monitor-grid">
        <section className="monitor-panel monitor-consumption">
          <header>
            <div>
              <p>PROFILO DI CONSUMO</p>
              <h2>Energia nel periodo</h2>
            </div>
            <span>{number(energy.import_kwh, 2)} kWh totali</span>
          </header>
          <SparkBars points={report?.timeline || []} />
        </section>
        <section className="monitor-panel monitor-health">
          <header>
            <div>
              <p>AFFIDABILITÀ</p>
              <h2>Qualità del bilancio</h2>
            </div>
            <span className={qualityGood ? "good" : "warn"}>
              {qualityGood ? "Affidabile" : "Da verificare"}
            </span>
          </header>
          <div
            className="quality-ring"
            style={
              {
                "--coverage": `${Math.min(power.coverage_percent || 0, 100) * 3.6}deg`,
              } as React.CSSProperties
            }
          >
            <strong>
              {number(power.coverage_percent, 0)}
              <small>%</small>
            </strong>
            <span>copertura</span>
          </div>
          <ul>
            <li>
              <span>Qualità contatore</span>
              <b>{energy.quality || "missing"}</b>
            </li>
            <li>
              <span>Campioni potenza</span>
              <b>{power.samples || 0}</b>
            </li>
            <li>
              <span>Reset contatore rilevati</span>
              <b>{energy.counter_resets || 0}</b>
            </li>
          </ul>
        </section>
        <section className="monitor-panel monitor-breakdown">
          <header>
            <div>
              <p>ENERGY TREE</p>
              <h2>Ripartizione per utenza</h2>
            </div>
            <span>Top 20</span>
          </header>
          {report?.breakdown?.length ? (
            <div className="breakdown-list">
              {report.breakdown.map((item: any) => (
                <article key={`${item.asset_id}-${item.device_id}`}>
                  <div>
                    <Factory />
                    <span>
                      <b>{item.asset_name}</b>
                      <small>
                        {item.device_name} · {item.quality}
                      </small>
                    </span>
                    <strong>{number(item.energy_kwh, 2)} kWh</strong>
                  </div>
                  <i>
                    <em
                      style={{
                        width: `${(item.energy_kwh / maxBreakdown) * 100}%`,
                      }}
                    />
                  </i>
                </article>
              ))}
            </div>
          ) : (
            <div className="monitor-empty">
              Associa i contatori secondari all’albero impianto per ottenere la
              ripartizione.
            </div>
          )}
          <footer>
            <span>Energia non attribuita</span>
            <strong className={energy.unattributed_kwh < 0 ? "bad" : ""}>
              {number(energy.unattributed_kwh, 2)} kWh
            </strong>
          </footer>
        </section>
        <section className="monitor-panel monitor-performance">
          <header>
            <div>
              <p>PERFORMANCE</p>
              <h2>Efficienza e obiettivi</h2>
            </div>
            <Sun />
          </header>
          <div className="performance-grid">
            <article>
              <span>Produzione FV</span>
              <strong>
                {number(energy.production_kwh)} <small>kWh</small>
              </strong>
            </article>
            <article>
              <span>Autoconsumo</span>
              <strong>
                {number(energy.self_consumption_percent)} <small>%</small>
              </strong>
            </article>
            <article>
              <span>Autosufficienza</span>
              <strong>
                {number(energy.self_sufficiency_percent)} <small>%</small>
              </strong>
            </article>
            <article>
              <span>Fuori orario</span>
              <strong>
                {number(energy.off_hours_kwh)} <small>kWh</small>
              </strong>
            </article>
          </div>
          <div className="budget">
            <div>
              <span>Budget energia mensile</span>
              <b>
                {budget.monthly_energy_budget_kwh
                  ? `${number(budget.projected_month_energy_kwh)} / ${number(budget.monthly_energy_budget_kwh)} kWh`
                  : "Non impostato"}
              </b>
            </div>
            <i>
              <em
                style={{
                  width: `${Math.min(budget.projected_energy_percent || 0, 100)}%`,
                }}
                className={
                  (budget.projected_energy_percent || 0) > 100 ? "over" : ""
                }
              />
            </i>
            <small>
              {budget.projected_energy_percent
                ? `Proiezione al ${number(budget.projected_energy_percent, 0)}% dell’obiettivo`
                : "Disponibile nella vista mensile"}
            </small>
          </div>
        </section>
      </div>
      {settingsOpen && draft && (
        <div className="monitor-modal" role="dialog" aria-modal="true">
          <form onSubmit={save}>
            <header>
              <div>
                <p>CONFIGURAZIONE</p>
                <h2>Parametri energetici</h2>
                <span>Applicati a report, budget e indicatori ambientali.</span>
              </div>
              <button
                type="button"
                onClick={() => setSettingsOpen(false)}
                aria-label="Chiudi"
              >
                <X />
              </button>
            </header>
            <div className="settings-fields">
              <label>
                Valuta
                <input
                  value={draft.currency}
                  maxLength={3}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      currency: e.target.value.toUpperCase(),
                    })
                  }
                />
              </label>
              <label>
                Tariffa prelievo <small>€/kWh</small>
                <input
                  type="number"
                  min="0"
                  step="0.0001"
                  value={draft.import_price_per_kwh}
                  onChange={(e) =>
                    setDraft({ ...draft, import_price_per_kwh: e.target.value })
                  }
                />
              </label>
              <label>
                Valore immissione <small>€/kWh</small>
                <input
                  type="number"
                  min="0"
                  step="0.0001"
                  value={draft.export_price_per_kwh}
                  onChange={(e) =>
                    setDraft({ ...draft, export_price_per_kwh: e.target.value })
                  }
                />
              </label>
              <label>
                Fattore emissione <small>kgCO₂e/kWh</small>
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={draft.co2_kg_per_kwh}
                  onChange={(e) =>
                    setDraft({ ...draft, co2_kg_per_kwh: e.target.value })
                  }
                />
              </label>
              <label>
                Potenza contrattuale <small>kW</small>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={draft.contracted_power_kw ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, contracted_power_kw: e.target.value })
                  }
                />
              </label>
              <label>
                Budget energia mese <small>kWh</small>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={draft.monthly_energy_budget_kwh ?? ""}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      monthly_energy_budget_kwh: e.target.value,
                    })
                  }
                />
              </label>
              <label>
                Budget costo mese <small>{draft.currency}</small>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={draft.monthly_cost_budget ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, monthly_cost_budget: e.target.value })
                  }
                />
              </label>
              <label>
                Fuso orario
                <input
                  value={draft.timezone}
                  onChange={(e) =>
                    setDraft({ ...draft, timezone: e.target.value })
                  }
                />
              </label>
              <label>
                Inizio attività
                <input
                  type="time"
                  value={draft.workday_start}
                  onChange={(e) =>
                    setDraft({ ...draft, workday_start: e.target.value })
                  }
                />
              </label>
              <label>
                Fine attività
                <input
                  type="time"
                  value={draft.workday_end}
                  onChange={(e) =>
                    setDraft({ ...draft, workday_end: e.target.value })
                  }
                />
              </label>
            </div>
            <fieldset>
              <legend>Giorni lavorativi</legend>
              {days.map((label, index) => (
                <button
                  type="button"
                  key={index}
                  className={draft.working_days.includes(index) ? "active" : ""}
                  onClick={() =>
                    setDraft({
                      ...draft,
                      working_days: draft.working_days.includes(index)
                        ? draft.working_days.filter(
                            (day: number) => day !== index,
                          )
                        : [...draft.working_days, index].sort(),
                    })
                  }
                >
                  {label}
                </button>
              ))}
            </fieldset>
            <footer>
              <span>
                <CalendarDays /> Questi valori sono il fallback; le fasce
                effettive si gestiscono in Tariffe e baseline.
              </span>
              <button disabled={saving}>
                <Save />
                {saving ? "Salvataggio…" : "Salva parametri"}
              </button>
            </footer>
          </form>
        </div>
      )}
    </div>
  );
}
