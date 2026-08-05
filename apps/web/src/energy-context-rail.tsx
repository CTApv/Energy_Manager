import { useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  BatteryCharging,
  ChevronDown,
  ChevronRight,
  CircleGauge,
  Gauge,
  HousePlug,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  SunMedium,
  Unplug,
  Zap,
} from "lucide-react";
import "./energy-context-rail.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";

type Props = {
  token: string;
  onOpenLive: () => void;
};

const categoryIcons: Record<string, any> = {
  solar: SunMedium,
  pv: SunMedium,
  storage: BatteryCharging,
  ev: HousePlug,
  meter: CircleGauge,
};

function number(value: unknown, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("it-IT", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : "—";
}

function flatten(nodes: any[]): any[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children || [])]);
}

function DeviceLeaf({
  device,
  depth,
  onOpenLive,
}: {
  device: any;
  depth: number;
  onOpenLive: () => void;
}) {
  const Icon = categoryIcons[device.category] || CircleGauge;
  return (
    <button
      className="energy-device-leaf"
      style={{ "--tree-depth": depth } as CSSProperties}
      onClick={onOpenLive}
    >
      <span className={`tree-device-icon status-${device.status}`}>
        <Icon />
      </span>
      <span>
        <b>{device.name}</b>
        <small>
          {device.manufacturer} {device.model}
        </small>
      </span>
      <strong>{number(device.power_kw)} kW</strong>
    </button>
  );
}

function TreeNode({
  node,
  depth,
  onOpenLive,
}: {
  node: any;
  depth: number;
  onOpenLive: () => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const children = node.children || [];
  const Icon = categoryIcons[node.category] || Zap;
  const status =
    node.meter?.status || (node.meters?.length ? "unknown" : "virtual");
  return (
    <div className="energy-tree-branch">
      <div
        className="energy-tree-node"
        style={{ "--tree-depth": depth } as CSSProperties}
      >
        <button
          className="tree-expander"
          onClick={() => setExpanded((value) => !value)}
          disabled={!children.length}
          aria-label={expanded ? "Comprimi ramo" : "Espandi ramo"}
        >
          {children.length ? (
            expanded ? (
              <ChevronDown />
            ) : (
              <ChevronRight />
            )
          ) : (
            <span />
          )}
        </button>
        <button className="tree-device" onClick={onOpenLive}>
          <span className={`tree-device-icon status-${status}`}>
            <Icon />
          </span>
          <span className="tree-device-copy">
            <b>{node.name}</b>
            <small>
              {node.meter
                ? `${node.meter.manufacturer} ${node.meter.model}`
                : "Nodo energetico aggregato"}
            </small>
          </span>
          <span className="tree-device-value">
            <b>{number(node.effective_power_kw)} kW</b>
            <small>{number(node.effective_energy_24h_kwh)} kWh oggi</small>
          </span>
        </button>
      </div>
      {expanded && children.length > 0 && (
        <div className="energy-tree-children">
          {children.map((child: any) => (
            <TreeNode
              key={child.id}
              node={child}
              depth={depth + 1}
              onOpenLive={onOpenLive}
            />
          ))}
        </div>
      )}
      {expanded &&
        (node.meters || [])
          .slice(1)
          .map((device: any) => (
            <DeviceLeaf
              key={device.id}
              device={device}
              depth={depth + 1}
              onOpenLive={onOpenLive}
            />
          ))}
    </div>
  );
}

export function EnergyContextRail({ token, onOpenLive }: Props) {
  const [open, setOpen] = useState(
    () => localStorage.getItem("em-energy-rail-open") !== "false",
  );
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      const response = await fetch(`${apiBase}/operations/tree`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error("Dati live non disponibili");
      setData(await response.json());
      setError("");
    } catch (loadError: any) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 5000);
    return () => window.clearInterval(timer);
  }, [token]);

  useEffect(() => {
    localStorage.setItem("em-energy-rail-open", String(open));
  }, [open]);

  const allNodes = useMemo(() => flatten(data?.roots || []), [data]);
  const allDevices = useMemo(
    () => [
      ...allNodes.flatMap((node) => node.meters || []),
      ...(data?.unassigned_devices || []),
    ],
    [allNodes, data],
  );
  const online = allDevices.filter(
    (device) => device.status === "online",
  ).length;
  const totalDevices = allDevices.length;

  return (
    <>
      {open && (
        <button
          className="energy-rail-backdrop"
          aria-label="Chiudi pannello energia"
          onClick={() => setOpen(false)}
        />
      )}
      <div
        className={`energy-context-rail ${open ? "open" : "closed"}`}
        role="complementary"
        aria-label="Albero energetico live"
      >
        <button
          className="energy-rail-toggle"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          title={open ? "Chiudi albero energetico" : "Apri albero energetico"}
        >
          {open ? <PanelRightClose /> : <PanelRightOpen />}
          {!open && <span>LIVE</span>}
        </button>
        <div className="energy-rail-inner">
          <header>
            <div>
              <span className="live-pulse">
                <i /> LIVE · 5 S
              </span>
              <h2>Albero energetico</h2>
              <p>Flusso monte-valle e misure essenziali.</p>
            </div>
            <button onClick={() => void load()} title="Aggiorna ora">
              <RefreshCw className={loading ? "spin" : ""} />
            </button>
          </header>

          <section className="energy-rail-totals">
            <article>
              <Zap />
              <span>
                <small>Potenza ecosistema</small>
                <b>
                  {number(data?.plant?.power_kw)} <em>kW</em>
                </b>
              </span>
            </article>
            <article>
              <Gauge />
              <span>
                <small>Energia 24 ore</small>
                <b>
                  {number(data?.plant?.energy_24h_kwh)} <em>kWh</em>
                </b>
              </span>
            </article>
          </section>

          <div className="energy-rail-health">
            <span>
              <i className="online" /> {online}/{totalDevices} online
            </span>
            <span>{data?.roots?.length || 0} rami principali</span>
          </div>

          {error ? (
            <div className="energy-rail-error">
              <Unplug />
              <span>
                <b>Flusso interrotto</b>
                <small>{error}</small>
              </span>
            </div>
          ) : (
            <>
              <section className="energy-rail-section tree-section">
                <div className="energy-rail-heading">
                  <span>Albero live</span>
                  <small>MONTE → VALLE</small>
                </div>
                <div className="energy-tree">
                  {(data?.roots || []).map((node: any) => (
                    <TreeNode
                      key={node.id}
                      node={node}
                      depth={0}
                      onOpenLive={onOpenLive}
                    />
                  ))}
                  {!loading && !data?.roots?.length && (
                    <p className="energy-rail-empty">
                      L'albero è vuoto. Avvia il commissioning per creare il
                      primo ramo.
                    </p>
                  )}
                </div>
              </section>

              {!!data?.unassigned_devices?.length && (
                <section className="energy-rail-section unassigned-section">
                  <div className="energy-rail-heading">
                    <span>Da collocare</span>
                    <small>{data.unassigned_devices.length} DISPOSITIVI</small>
                  </div>
                  {data.unassigned_devices.map((device: any) => (
                    <DeviceLeaf
                      key={device.id}
                      device={device}
                      depth={0}
                      onOpenLive={onOpenLive}
                    />
                  ))}
                </section>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
