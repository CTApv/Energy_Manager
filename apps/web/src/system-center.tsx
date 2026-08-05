import {
  Activity,
  CheckCircle2,
  Clock3,
  Database,
  Gauge,
  HardDrive,
  Languages,
  Moon,
  RefreshCw,
  Save,
  Server,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { useEffect, useState } from "react";
import "./system-center.css";
import { applyTheme, type ThemePreference } from "./theme";

const apiBase = import.meta.env.VITE_API_URL || "/api";
async function api(path: string, token: string, options: RequestInit = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => ({}))).detail ||
        "Operazione non riuscita",
    );
  return response.json();
}
const days = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];

export function SystemCenter({
  token,
  focus = "status",
}: {
  token: string;
  focus?: "status" | "preferences";
}) {
  const [system, setSystem] = useState<any>(null),
    [energy, setEnergy] = useState<any>(null),
    [tab, setTab] = useState(focus),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const load = async () => {
    setError("");
    try {
      const [s, e] = await Promise.all([
        api("/system/overview", token),
        api("/energy/settings", token),
      ]);
      setSystem(s);
      setEnergy(e);
    } catch (e: any) {
      setError(e.message);
    }
  };
  useEffect(() => {
    setTab(focus);
  }, [focus]);
  useEffect(() => {
    void load();
  }, [token]);
  const selectTheme = (theme: ThemePreference) => {
    setSystem({ ...system, preferences: { ...system.preferences, theme } });
    applyTheme(theme);
  };
  async function savePreferences(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await Promise.all([
        api("/system/preferences", token, {
          method: "PUT",
          body: JSON.stringify(system.preferences),
        }),
        api("/energy/settings", token, {
          method: "PUT",
          body: JSON.stringify({
            ...energy,
            contracted_power_kw: energy.contracted_power_kw || null,
            monthly_energy_budget_kwh: energy.monthly_energy_budget_kwh || null,
            monthly_cost_budget: energy.monthly_cost_budget || null,
          }),
        }),
      ]);
      setMessage("Preferenze salvate");
      setTimeout(() => setMessage(""), 3500);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!system || !energy)
    return <div className="loading">Caricamento configurazione…</div>;
  const storage = system.storage || {},
    percent = storage.total_bytes
      ? Math.round((storage.used_bytes / storage.total_bytes) * 100)
      : 0;
  return (
    <div className="system-center">
      <header className="system-head">
        <div>
          <p>AMMINISTRAZIONE EDGE</p>
          <h1>{tab === "status" ? "Stato sistema" : "Preferenze"}</h1>
          <span>
            Informazioni utili e impostazioni operative, senza parametri tecnici
            fuori contesto.
          </span>
        </div>
        <button className="icon-button" onClick={load}>
          <RefreshCw />
          Aggiorna
        </button>
      </header>
      {message && (
        <div className="notice">
          <CheckCircle2 />
          {message}
        </div>
      )}
      {error && <div className="alert">{error}</div>}
      <nav className="section-tabs">
        <button
          className={tab === "status" ? "active" : ""}
          onClick={() => setTab("status")}
        >
          <Activity />
          Stato Edge
        </button>
        <button
          className={tab === "preferences" ? "active" : ""}
          onClick={() => setTab("preferences")}
        >
          <Gauge />
          Preferenze operative
        </button>
      </nav>
      {tab === "status" && (
        <>
          <div className="system-metrics">
            <article>
              <span>
                <ShieldCheck />
              </span>
              <div>
                <small>Servizio</small>
                <b>Operativo</b>
              </div>
              <em className="ok">OK</em>
            </article>
            <article>
              <span>
                <Server />
              </span>
              <div>
                <small>Versione</small>
                <b>{system.release}</b>
              </div>
              <em>{system.environment}</em>
            </article>
            <article>
              <span>
                <Database />
              </span>
              <div>
                <small>Database</small>
                <b>{system.database === "ok" ? "Integro" : "Da verificare"}</b>
              </div>
              <em className={system.database === "ok" ? "ok" : "bad"}>
                {system.database}
              </em>
            </article>
            <article>
              <span>
                <HardDrive />
              </span>
              <div>
                <small>Spazio utilizzato</small>
                <b>{percent}%</b>
              </div>
              <em>{storage.free_gb ?? "—"} GB liberi</em>
            </article>
          </div>
          <div className="system-grid">
            <section className="panel">
              <header>
                <h2>Identità Edge</h2>
              </header>
              <dl className="clean-details">
                <div>
                  <dt>Nome host</dt>
                  <dd>{system.runtime.hostname}</dd>
                </div>
                <div>
                  <dt>Sistema operativo</dt>
                  <dd>
                    {system.runtime.operating_system}{" "}
                    {system.runtime.os_release}
                  </dd>
                </div>
                <div>
                  <dt>Architettura</dt>
                  <dd>{system.runtime.architecture}</dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd>Python {system.runtime.python}</dd>
                </div>
                <div>
                  <dt>Sviluppo software</dt>
                  <dd>Filippo Lolli</dd>
                </div>
              </dl>
            </section>
            <section className="panel">
              <header>
                <h2>Capacità locale</h2>
              </header>
              <div className="storage-card">
                <div
                  className="storage-ring"
                  style={{ "--used": `${percent * 3.6}deg` } as any}
                >
                  <span>{percent}%</span>
                </div>
                <div>
                  <b>{storage.used_gb ?? "—"} GB utilizzati</b>
                  <small>su {storage.total_gb ?? "—"} GB disponibili</small>
                  <div className="storage-bar">
                    <i style={{ width: `${percent}%` }} />
                  </div>
                  <em>
                    Retention automatica dati:{" "}
                    {energy.retention_days || "configurata dal sistema"}
                  </em>
                </div>
              </div>
            </section>
          </div>
        </>
      )}
      {tab === "preferences" && (
        <form className="preferences-layout" onSubmit={savePreferences}>
          <section className="panel preference-card">
            <header>
              <span>
                <Languages />
              </span>
              <div>
                <h2>Esperienza d’uso</h2>
                <p>Aspetto e frequenza di aggiornamento della postazione.</p>
              </div>
            </header>
            <div className="form-grid">
              <label>
                Lingua
                <select
                  value={system.preferences.language}
                  onChange={(e) =>
                    setSystem({
                      ...system,
                      preferences: {
                        ...system.preferences,
                        language: e.target.value,
                      },
                    })
                  }
                >
                  <option value="it">Italiano</option>
                  <option value="en">English</option>
                </select>
              </label>
              <label>
                Aggiornamento dati
                <select
                  value={system.preferences.refresh_seconds}
                  onChange={(e) =>
                    setSystem({
                      ...system,
                      preferences: {
                        ...system.preferences,
                        refresh_seconds: Number(e.target.value),
                      },
                    })
                  }
                >
                  <option value="2">2 secondi</option>
                  <option value="5">5 secondi</option>
                  <option value="10">10 secondi</option>
                  <option value="30">30 secondi</option>
                </select>
              </label>
              <div className="wide theme-picker">
                <button
                  type="button"
                  className={
                    system.preferences.theme === "light" ? "active" : ""
                  }
                  onClick={() => selectTheme("light")}
                >
                  <Sun />
                  Chiaro
                </button>
                <button
                  type="button"
                  className={
                    system.preferences.theme === "dark" ? "active" : ""
                  }
                  onClick={() => selectTheme("dark")}
                >
                  <Moon />
                  Scuro
                </button>
                <button
                  type="button"
                  className={
                    system.preferences.theme === "system" ? "active" : ""
                  }
                  onClick={() => selectTheme("system")}
                >
                  <Activity />
                  Sistema
                </button>
              </div>
            </div>
          </section>
          <section className="panel preference-card">
            <header>
              <span>
                <Clock3 />
              </span>
              <div>
                <h2>Calendario energetico</h2>
                <p>Serve a distinguere consumi in orario e fuori orario.</p>
              </div>
            </header>
            <div className="form-grid">
              <label className="wide">
                Fuso orario
                <input
                  value={energy.timezone}
                  onChange={(e) =>
                    setEnergy({ ...energy, timezone: e.target.value })
                  }
                />
              </label>
              <label>
                Inizio attività
                <input
                  type="time"
                  value={energy.workday_start}
                  onChange={(e) =>
                    setEnergy({ ...energy, workday_start: e.target.value })
                  }
                />
              </label>
              <label>
                Fine attività
                <input
                  type="time"
                  value={energy.workday_end}
                  onChange={(e) =>
                    setEnergy({ ...energy, workday_end: e.target.value })
                  }
                />
              </label>
              <div className="wide day-picker">
                {days.map((day, index) => (
                  <button
                    type="button"
                    key={day}
                    className={
                      energy.working_days.includes(index) ? "active" : ""
                    }
                    onClick={() =>
                      setEnergy({
                        ...energy,
                        working_days: energy.working_days.includes(index)
                          ? energy.working_days.filter(
                              (x: number) => x !== index,
                            )
                          : [...energy.working_days, index].sort(),
                      })
                    }
                  >
                    {day}
                  </button>
                ))}
              </div>
            </div>
          </section>
          <section className="panel preference-card">
            <header>
              <span>
                <Gauge />
              </span>
              <div>
                <h2>Contratto e obiettivi</h2>
                <p>Parametri usati per costi, budget e indicatori.</p>
              </div>
            </header>
            <div className="form-grid">
              <label>
                Valuta
                <input
                  value={energy.currency}
                  maxLength={3}
                  onChange={(e) =>
                    setEnergy({
                      ...energy,
                      currency: e.target.value.toUpperCase(),
                    })
                  }
                />
              </label>
              <label>
                Potenza impegnata (kW)
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={energy.contracted_power_kw || ""}
                  onChange={(e) =>
                    setEnergy({
                      ...energy,
                      contracted_power_kw: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Acquisto energia / kWh
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={energy.import_price_per_kwh}
                  onChange={(e) =>
                    setEnergy({
                      ...energy,
                      import_price_per_kwh: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Immissione energia / kWh
                <input
                  type="number"
                  min="0"
                  step="0.001"
                  value={energy.export_price_per_kwh}
                  onChange={(e) =>
                    setEnergy({
                      ...energy,
                      export_price_per_kwh: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Budget mensile energia (kWh)
                <input
                  type="number"
                  min="0"
                  value={energy.monthly_energy_budget_kwh || ""}
                  onChange={(e) =>
                    setEnergy({
                      ...energy,
                      monthly_energy_budget_kwh: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Budget mensile costo
                <input
                  type="number"
                  min="0"
                  value={energy.monthly_cost_budget || ""}
                  onChange={(e) =>
                    setEnergy({
                      ...energy,
                      monthly_cost_budget: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
          </section>
          <footer className="preferences-save">
            <span>Le modifiche sono registrate nell’audit log.</span>
            <button className="primary-button" disabled={busy}>
              <Save />
              {busy ? "Salvataggio…" : "Salva preferenze"}
            </button>
          </footer>
        </form>
      )}
    </div>
  );
}
