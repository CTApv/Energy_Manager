import { useEffect, useState } from "react";
import {
  CalendarRange,
  CircleDollarSign,
  Plus,
  Trash2,
  TrendingDown,
} from "lucide-react";
import "./energy-planning.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";
type Item = Record<string, any>;

async function call(path: string, token: string, options: RequestInit = {}) {
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
        `Errore ${response.status}`,
    );
  return response.json();
}

export function EnergyPlanning({
  token,
  editable,
}: {
  token: string;
  editable: boolean;
}) {
  const [tariffs, setTariffs] = useState<Item[]>([]);
  const [baselines, setBaselines] = useState<Item[]>([]);
  const [evaluation, setEvaluation] = useState<Item | null>(null);
  const [error, setError] = useState("");
  const [panel, setPanel] = useState<"tariff" | "baseline" | null>(null);
  const load = async () => {
    try {
      const [t, b] = await Promise.all([
        call("/energy/tariffs", token),
        call("/energy/baselines", token),
      ]);
      setTariffs(t);
      setBaselines(b);
      setError("");
    } catch (e: any) {
      setError(e.message);
    }
  };
  useEffect(() => {
    void load();
  }, [token]);

  async function createTariff(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await call("/energy/tariffs", token, {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        valid_from: new Date(String(form.get("valid_from"))).toISOString(),
        valid_to: form.get("valid_to")
          ? new Date(String(form.get("valid_to"))).toISOString()
          : null,
        weekdays: [0, 1, 2, 3, 4, 5, 6],
        start_minute: Number(form.get("start_minute")),
        end_minute: Number(form.get("end_minute")),
        import_price_per_kwh: Number(form.get("import_price")),
        export_price_per_kwh: Number(form.get("export_price")),
        priority: Number(form.get("priority")),
        active: true,
      }),
    });
    setPanel(null);
    await load();
  }

  async function createBaseline(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await call("/energy/baselines", token, {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        measurement_key: "electrical.energy.import_total",
        period_start: new Date(String(form.get("period_start"))).toISOString(),
        period_end: new Date(String(form.get("period_end"))).toISOString(),
        baseline_value: Number(form.get("baseline_value")),
        unit: "kWh",
        normalization: {
          method: "manual_reference_period",
          note: String(form.get("note") || ""),
        },
        active: true,
      }),
    });
    setPanel(null);
    await load();
  }

  async function remove(kind: "tariffs" | "baselines", id: string) {
    if (
      !confirm(
        "Confermi l'eliminazione? L'operazione sarà registrata nell'audit log.",
      )
    )
      return;
    await call(`/energy/${kind}/${id}`, token, { method: "DELETE" });
    await load();
  }

  return (
    <div className="planning-page">
      <header className="planning-hero">
        <div>
          <p className="eyebrow">GOVERNANCE ENERGETICA</p>
          <h1>Tariffe e baseline</h1>
          <p>
            Trasforma le misure in costi, obiettivi verificabili e indicatori di
            miglioramento.
          </p>
        </div>
        <CalendarRange size={42} />
      </header>
      {error && <p className="error">{error}</p>}
      <section className="planning-grid">
        <article className="planning-card">
          <div className="planning-heading">
            <div>
              <CircleDollarSign />
              <span>
                <b>Piani tariffari</b>
                <small>
                  Fasce con validità, priorità e valorizzazione dell'immissione
                </small>
              </span>
            </div>
            {editable && (
              <button onClick={() => setPanel("tariff")}>
                <Plus size={17} /> Nuova fascia
              </button>
            )}
          </div>
          <div className="planning-list">
            {tariffs.length ? (
              tariffs.map((t) => (
                <div className="planning-row" key={t.id}>
                  <span>
                    <b>{t.name}</b>
                    <small>
                      {minute(t.start_minute)}–{minute(t.end_minute)} · priorità{" "}
                      {t.priority}
                    </small>
                  </span>
                  <strong>
                    € {Number(t.import_price_per_kwh).toFixed(3)}/kWh
                  </strong>
                  {editable && (
                    <button
                      className="icon-action"
                      aria-label="Elimina tariffa"
                      onClick={() => remove("tariffs", t.id)}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))
            ) : (
              <Empty text="Nessuna fascia configurata" />
            )}
          </div>
        </article>
        <article className="planning-card">
          <div className="planning-heading">
            <div>
              <TrendingDown />
              <span>
                <b>Baseline energetiche</b>
                <small>
                  Periodi di riferimento versionati e scostamento corrente
                </small>
              </span>
            </div>
            {editable && (
              <button onClick={() => setPanel("baseline")}>
                <Plus size={17} /> Nuova baseline
              </button>
            )}
          </div>
          <div className="planning-list">
            {baselines.length ? (
              baselines.map((b) => (
                <div className="planning-row baseline" key={b.id}>
                  <span>
                    <b>{b.name}</b>
                    <small>
                      {new Date(b.period_start).toLocaleDateString("it-IT")}–
                      {new Date(b.period_end).toLocaleDateString("it-IT")}
                    </small>
                  </span>
                  <strong>
                    {Number(b.baseline_value).toLocaleString("it-IT")} {b.unit}
                  </strong>
                  <button
                    className="secondary"
                    onClick={async () =>
                      setEvaluation(
                        await call(
                          `/energy/baselines/${b.id}/evaluate?period=month`,
                          token,
                        ),
                      )
                    }
                  >
                    Valuta
                  </button>
                  {editable && (
                    <button
                      className="icon-action"
                      aria-label="Elimina baseline"
                      onClick={() => remove("baselines", b.id)}
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              ))
            ) : (
              <Empty text="Nessuna baseline congelata" />
            )}
          </div>
        </article>
      </section>
      {evaluation && (
        <aside className="evaluation">
          <button className="close" onClick={() => setEvaluation(null)}>
            ×
          </button>
          <p className="eyebrow">SCOSTAMENTO PERIODO</p>
          <h2>{evaluation.baseline?.name}</h2>
          <div>
            <span>
              <small>Baseline</small>
              <b>{fmt(evaluation.baseline?.baseline_value)} kWh</b>
            </span>
            <span>
              <small>Consumo misurato</small>
              <b>{fmt(evaluation.actual_value)} kWh</b>
            </span>
            <span className={(evaluation.variance || 0) <= 0 ? "good" : "warn"}>
              <small>Scostamento</small>
              <b>{fmt(evaluation.variance_percent)}%</b>
            </span>
          </div>
          <p>
            Qualità dato: <b>{evaluation.quality || "non disponibile"}</b>. La
            normalizzazione avanzata va validata da un professionista sul
            contesto d'uso.
          </p>
        </aside>
      )}
      {panel && (
        <div className="planning-modal" role="dialog" aria-modal="true">
          <form onSubmit={panel === "tariff" ? createTariff : createBaseline}>
            <button
              type="button"
              className="close"
              onClick={() => setPanel(null)}
            >
              ×
            </button>
            <h2>
              {panel === "tariff"
                ? "Nuova fascia tariffaria"
                : "Nuova baseline"}
            </h2>
            {panel === "tariff" ? (
              <>
                <label>
                  Nome
                  <input name="name" required placeholder="F1 feriale" />
                </label>
                <div className="form-pair">
                  <label>
                    Valida dal
                    <input name="valid_from" type="datetime-local" required />
                  </label>
                  <label>
                    Valida fino al
                    <input name="valid_to" type="datetime-local" />
                  </label>
                </div>
                <div className="form-pair">
                  <label>
                    Da minuto
                    <input
                      name="start_minute"
                      type="number"
                      defaultValue="0"
                      min="0"
                      max="1439"
                      required
                    />
                  </label>
                  <label>
                    A minuto
                    <input
                      name="end_minute"
                      type="number"
                      defaultValue="1440"
                      min="1"
                      max="1440"
                      required
                    />
                  </label>
                </div>
                <div className="form-pair">
                  <label>
                    Prelievo €/kWh
                    <input
                      name="import_price"
                      type="number"
                      step="0.001"
                      min="0"
                      required
                    />
                  </label>
                  <label>
                    Immissione €/kWh
                    <input
                      name="export_price"
                      type="number"
                      step="0.001"
                      min="0"
                      defaultValue="0"
                      required
                    />
                  </label>
                </div>
                <label>
                  Priorità
                  <input
                    name="priority"
                    type="number"
                    min="0"
                    max="1000"
                    defaultValue="0"
                    required
                  />
                </label>
              </>
            ) : (
              <>
                <label>
                  Nome
                  <input name="name" required placeholder="Baseline 2025" />
                </label>
                <div className="form-pair">
                  <label>
                    Inizio periodo
                    <input name="period_start" type="datetime-local" required />
                  </label>
                  <label>
                    Fine periodo
                    <input name="period_end" type="datetime-local" required />
                  </label>
                </div>
                <label>
                  Energia di riferimento (kWh)
                  <input
                    name="baseline_value"
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                  />
                </label>
                <label>
                  Nota di normalizzazione
                  <textarea
                    name="note"
                    placeholder="Occupazione, gradi giorno, ore di produzione…"
                  />
                </label>
              </>
            )}
            <button type="submit">Salva configurazione</button>
          </form>
        </div>
      )}
    </div>
  );
}

function minute(value: number) {
  return value === 1440
    ? "24:00"
    : `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}
function fmt(value: any) {
  return value == null
    ? "—"
    : Number(value).toLocaleString("it-IT", { maximumFractionDigits: 1 });
}
function Empty({ text }: { text: string }) {
  return <div className="planning-empty">{text}</div>;
}
