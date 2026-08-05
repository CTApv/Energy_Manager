import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BatteryCharging,
  Bolt,
  CarFront,
  ChevronRight,
  CloudSun,
  Factory,
  Gauge,
  Grid3X3,
  Leaf,
  Radio,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sun,
  Zap,
} from "lucide-react";
import "./energy-studio.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";
async function api(path: string, token: string) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok)
    throw new Error(
      (await response.json().catch(() => ({}))).detail ||
        "Dati non disponibili",
    );
  return response.json();
}
const fmt = (value: any, digits = 1) =>
  value === null || value === undefined
    ? "—"
    : Number(value).toLocaleString("it-IT", { maximumFractionDigits: digits });

const categoryMeta: Record<string, { label: string; icon: any; tone: string }> =
  {
    multimeter: { label: "Rete e misure", icon: Gauge, tone: "cyan" },
    pv_inverter: { label: "Fotovoltaico", icon: Sun, tone: "solar" },
    battery_storage: {
      label: "Accumulo",
      icon: BatteryCharging,
      tone: "violet",
    },
    ev_charger: { label: "Ricarica EV", icon: CarFront, tone: "blue" },
    environmental_sensor: {
      label: "Sensori ambientali",
      icon: CloudSun,
      tone: "green",
    },
    device: { label: "Altri dispositivi", icon: Radio, tone: "slate" },
  };

function FlowNode({
  kind,
  label,
  value,
  detail,
  active = true,
}: {
  kind: string;
  label: string;
  value: any;
  detail: string;
  active?: boolean;
}) {
  const meta = categoryMeta[kind] || categoryMeta.device,
    Icon = meta.icon;
  return (
    <article className={`flow-node ${meta.tone} ${active ? "active" : "idle"}`}>
      <span className="node-orbit" />
      <div className="flow-icon">
        <Icon />
      </div>
      <div>
        <span>{label}</span>
        <strong>
          {fmt(value)} <small>kW</small>
        </strong>
        <p>{detail}</p>
      </div>
    </article>
  );
}

function EnergyFlow({ flows }: { flows: any }) {
  const storage = Number(flows.storage_kw || 0);
  return (
    <section className="neo-card flow-card">
      <header>
        <div>
          <p>FLUSSI IN TEMPO REALE</p>
          <h2>Da dove arriva e dove va l’energia</h2>
        </div>
        <span className="telemetry-pulse">
          <i />
          Aggiornamento 5s
        </span>
      </header>
      <div className="flow-stage">
        <div className="flow-grid-source">
          <FlowNode
            kind="multimeter"
            label="Rete"
            value={Math.abs(flows.grid_kw || 0)}
            detail={
              flows.grid_direction === "export" ? "Immissione" : "Prelievo"
            }
          />
        </div>
        <div className="flow-solar">
          <FlowNode
            kind="pv_inverter"
            label="Fotovoltaico"
            value={flows.solar_kw}
            detail="Produzione AC"
            active={flows.solar_kw > 0}
          />
        </div>
        <div className="flow-hub">
          <span className="hub-rings" />
          <div>
            <Factory />
            <b>IMPIANTO</b>
            <strong>{fmt(flows.load_kw)} kW</strong>
            <small>domanda stimata</small>
          </div>
        </div>
        <div className="flow-storage">
          <FlowNode
            kind="battery_storage"
            label="Accumulo"
            value={Math.abs(storage)}
            detail={
              storage > 0 ? "Scarica" : storage < 0 ? "Carica" : "Stand-by"
            }
            active={storage !== 0}
          />
        </div>
        <div className="flow-ev">
          <FlowNode
            kind="ev_charger"
            label="Mobilità"
            value={flows.ev_kw}
            detail="Ricarica EV"
            active={flows.ev_kw > 0}
          />
        </div>
        <svg
          className="flow-lines"
          viewBox="0 0 1000 460"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path d="M235 105 C370 105 360 220 485 230" />
          <path d="M235 355 C370 355 360 250 485 235" />
          <path d="M765 105 C630 105 640 220 515 230" />
          <path d="M765 355 C630 355 640 250 515 235" />
        </svg>
        <span className="energy-particle p1" />
        <span className="energy-particle p2" />
        <span className="energy-particle p3" />
        <span className="energy-particle p4" />
      </div>
    </section>
  );
}

const colors = [
  "#4de3b2",
  "#ffd45d",
  "#8f7dff",
  "#4aa9ff",
  "#ff7e67",
  "#b9d46a",
  "#56d5ed",
  "#c28cff",
];
function FleetTrend({ analytics }: { analytics: any }) {
  const series = analytics?.series || [];
  const all = series
    .flatMap((item: any) => item.points.map((point: any) => Number(point.avg)))
    .filter(Number.isFinite);
  if (all.length < 2)
    return (
      <div className="studio-empty">
        <Radio />
        <b>Storico in preparazione</b>
        <span>
          I tracciati compariranno con campioni validi dai dispositivi.
        </span>
      </div>
    );
  const min = Math.min(...all),
    max = Math.max(...all),
    span = Math.max(max - min, 1);
  return (
    <div className="fleet-trend">
      <div className="trend-y">
        <span>{fmt(max)} kW</span>
        <span>{fmt((max + min) / 2)} kW</span>
        <span>{fmt(min)} kW</span>
      </div>
      <svg viewBox="0 0 900 260" preserveAspectRatio="none">
        <line x1="0" y1="35" x2="900" y2="35" />
        <line x1="0" y1="130" x2="900" y2="130" />
        <line x1="0" y1="225" x2="900" y2="225" />
        {series.map((item: any, index: number) => {
          const points = item.points
            .map(
              (point: any, i: number) =>
                `${(i * 900) / Math.max(item.points.length - 1, 1)},${225 - ((Number(point.avg) - min) / span) * 190}`,
            )
            .join(" ");
          return (
            <polyline
              key={`${item.device_id}-${item.key}`}
              points={points}
              fill="none"
              stroke={colors[index % colors.length]}
              strokeWidth="3"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
      </svg>
      <div className="trend-legend">
        {series.map((item: any, index: number) => (
          <span key={`${item.device_id}-${item.key}`}>
            <i style={{ background: colors[index % colors.length] }} />
            {item.device_name} · {item.key.split(".").at(-1)}
          </span>
        ))}
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  unit,
  detail,
  icon: Icon,
  tone,
}: {
  label: string;
  value: any;
  unit: string;
  detail: string;
  icon: any;
  tone: string;
}) {
  return (
    <article className={`studio-kpi ${tone}`}>
      <div>
        <span>{label}</span>
        <Icon />
      </div>
      <strong>
        {fmt(value)}{" "}
        <small>{value !== null && value !== undefined ? unit : ""}</small>
      </strong>
      <p>{detail}</p>
      <i className="kpi-glow" />
    </article>
  );
}

export function EnergyStudio({
  token,
  onOpenPlant,
  canManage,
}: {
  token: string;
  onOpenPlant: () => void;
  canManage: boolean;
}) {
  const [overview, setOverview] = useState<any>(null),
    [dashboard, setDashboard] = useState<any>(null),
    [analytics, setAnalytics] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(true);
  const load = async (silent = false) => {
    if (!silent) setBusy(true);
    setError("");
    try {
      const [energy, dash, history] = await Promise.all([
        api("/energy/overview", token),
        api("/dashboard", token),
        api(
          "/analytics/timeseries?hours=24&bucket_minutes=5&measurement_keys=electrical.active_power.total,pv.power.ac_total,storage.power.active,ev.power.active",
          token,
        ),
      ]);
      setOverview(energy);
      setDashboard(dash);
      setAnalytics(history);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(true), 5000);
    return () => clearInterval(timer);
  }, [token]);
  const grouped = useMemo(() => {
    const result: Record<string, any[]> = {};
    for (const item of overview?.inventory || [])
      (result[item.category] ??= []).push(item);
    return result;
  }, [overview]);
  if (busy && !overview)
    return (
      <div className="studio-loader">
        <span />
        <b>Inizializzazione Energy Command…</b>
        <small>Sincronizzazione dei flussi e degli asset</small>
      </div>
    );
  const flows = overview?.flows || {},
    kpis = overview?.kpis || {};
  return (
    <div className="energy-studio">
      <header className="studio-hero">
        <div>
          <p>ECOSISTEMA ENERGETICO · LIVE</p>
          <h1>{dashboard?.site_name || "Il tuo ecosistema energetico"}</h1>
          <span>
            Produzione, accumulo, mobilità e consumi in un unico ecosistema
          </span>
        </div>
        <div className="hero-actions">
          <span
            className={`system-live ${kpis.devices_degraded ? "warning" : ""}`}
          >
            <i />
            {kpis.devices_degraded
              ? `${kpis.devices_degraded} da verificare`
              : "Ecosistema connesso"}
          </span>
          <button onClick={() => void load()} title="Aggiorna">
            <RefreshCw />
          </button>
          {canManage && (
            <button className="hero-primary" onClick={onOpenPlant}>
              <Settings2 />
              Configura ecosistema
            </button>
          )}
        </div>
      </header>
      {error && (
        <div className="studio-error">
          <AlertTriangle />
          {error}
        </div>
      )}
      <div className="home-manifest">
        <div>
          <span>ENERGY HABITAT</span>
          <b>
            L’ecosistema non consuma soltanto energia.
            <br />
            La produce, la conserva e la distribuisce.
          </b>
        </div>
        <p>
          Una regia locale e privata coordina fotovoltaico, batteria, ricarica
          elettrica e utenze — anche senza cloud.
        </p>
      </div>
      <div className="studio-kpis">
        <Kpi
          label="Bilancio attuale"
          value={flows.load_kw}
          unit="kW"
          detail={`Dalla rete ${fmt(Math.abs(flows.grid_kw || 0))} kW`}
          icon={Bolt}
          tone="mint"
        />
        <Kpi
          label="Sole sul tetto"
          value={flows.solar_kw}
          unit="kW"
          detail={`Autoconsumo ${fmt(kpis.self_consumption_percent)}%`}
          icon={Sun}
          tone="solar"
        />
        <Kpi
          label="Riserva energetica"
          value={kpis.storage_soc_percent}
          unit="%"
          detail={`${flows.storage_direction || "inattiva"} · ${fmt(Math.abs(flows.storage_kw || 0))} kW`}
          icon={BatteryCharging}
          tone="violet"
        />
        <Kpi
          label="Indipendenza"
          value={kpis.renewable_share_percent}
          unit="%"
          detail={`${kpis.devices_online || 0}/${kpis.devices_total || 0} elementi connessi`}
          icon={Leaf}
          tone="cyan"
        />
      </div>
      <div className="studio-main">
        <EnergyFlow flows={flows} />
        <section className="neo-card intelligence-card">
          <header>
            <div>
              <p>QUIET TECHNOLOGY</p>
              <h2>La tecnologia che non disturba</h2>
            </div>
            <ShieldCheck />
          </header>
          <div className="intelligence-score">
            <div
              style={
                {
                  "--score": `${Math.max(0, 100 - (kpis.devices_degraded || 0) * 12)}%`,
                } as React.CSSProperties
              }
            >
              <strong>
                {Math.max(0, 100 - (kpis.devices_degraded || 0) * 12)}
              </strong>
              <small>/100</small>
            </div>
            <span>
              <b>Armonia energetica</b>
              <small>Continuità, qualità e autonomia</small>
            </span>
          </div>
          <div className="intelligence-list">
            <div>
              <Radio />
              <span>
                <b>Elementi connessi</b>
                <small>Acquisizione locale</small>
              </span>
              <strong>{kpis.devices_total || 0}</strong>
            </div>
            <div>
              <ShieldCheck />
              <span>
                <b>Dati affidabili</b>
                <small>Controllati in tempo reale</small>
              </span>
              <strong>
                {Math.max(
                  0,
                  (kpis.devices_total || 0) - (kpis.devices_degraded || 0),
                )}
              </strong>
            </div>
            <div>
              <AlertTriangle />
              <span>
                <b>Da osservare</b>
                <small>Anomalie o comunicazione</small>
              </span>
              <strong>{kpis.devices_degraded || 0}</strong>
            </div>
          </div>
        </section>
      </div>
      <div className="studio-lower">
        <section className="neo-card history-card">
          <header>
            <div>
              <p>IL RITMO DELLA CASA · 24H</p>
              <h2>Quando l’energia prende vita</h2>
            </div>
            <button>
              <Grid3X3 />
              Medie 5 min
            </button>
          </header>
          <FleetTrend analytics={analytics} />
        </section>
        <section className="neo-card asset-card">
          <header>
            <div>
              <p>IL TUO ECOSISTEMA</p>
              <h2>Fonti e servizi connessi</h2>
            </div>
            <span>{overview?.inventory?.length || 0} elementi</span>
          </header>
          <div className="asset-scroll">
            {Object.entries(grouped).map(([category, items]: any) => {
              const meta = categoryMeta[category] || categoryMeta.device,
                Icon = meta.icon;
              return (
                <div className="asset-group" key={category}>
                  <h3>
                    <Icon />
                    {meta.label}
                    <span>{items.length}</span>
                  </h3>
                  {items.map((item: any) => (
                    <article key={item.id}>
                      <i className={`asset-state ${item.status}`} />
                      <div>
                        <b>{item.name}</b>
                        <small>
                          {item.manufacturer} {item.model}
                        </small>
                      </div>
                      <strong>
                        {fmt(item.power_kw)} <small>kW</small>
                      </strong>
                      <ChevronRight />
                    </article>
                  ))}
                </div>
              );
            })}
            {!overview?.inventory?.length && (
              <div className="studio-empty compact">
                <Zap />
                <b>L’ecosistema attende il primo dispositivo</b>
                <span>
                  Un tecnico può avviare la ricerca dalla sezione Comunicazioni.
                </span>
              </div>
            )}
          </div>
        </section>
      </div>
      <footer className="studio-footer">
        <span>
          <ShieldCheck />
          Privata e locale
        </span>
        <span>
          <Radio />
          Operativa senza Internet
        </span>
        <span>
          <Leaf />
          Nata per l’energia rinnovabile
        </span>
      </footer>
    </div>
  );
}
