import React, { useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronRight,
  LoaderCircle,
  Network,
  Radar,
  Router,
  Search,
  ShieldCheck,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import "./modbus-discovery.css";
import "./modbus-discovery-transport.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";
async function api(path: string, token: string, options: RequestInit = {}) {
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
        "Operazione non riuscita",
    );
  return response.json();
}
const category = (value: string) =>
  ({
    multimeter: "Multimetro",
    pv_inverter: "Inverter FV",
    battery_storage: "Accumulo",
    ev_charger: "Ricarica EV",
    environmental_sensor: "Sensore",
  })[value] || value;

export function ModbusDiscovery({
  token,
  onClose,
  onInstalled,
}: {
  token: string;
  onClose: () => void;
  onInstalled: () => Promise<void> | void;
}) {
  const [form, setForm] = useState({
      network: "192.168.2.0/24",
      ports: "502, 5020",
      unit_from: 1,
      unit_to: 10,
      timeout_seconds: 0.35,
    }),
    [result, setResult] = useState<any>(null),
    [scanning, setScanning] = useState(false),
    [error, setError] = useState(""),
    [selected, setSelected] = useState<any>(null),
    [profileId, setProfileId] = useState(""),
    [deviceName, setDeviceName] = useState(""),
    [transport, setTransport] = useState<"modbus_tcp" | "modbus_rtu_tcp">(
      "modbus_tcp",
    ),
    [installing, setInstalling] = useState(false),
    [installed, setInstalled] = useState<string[]>([]);
  const devices = useMemo(
    () =>
      result?.endpoints?.flatMap((endpoint: any) =>
        endpoint.units.map((unit: any) => ({
          ...unit,
          host: endpoint.host,
          port: endpoint.port,
        })),
      ) || [],
    [result],
  );
  const compatibleCandidates = (selected?.profile_candidates || []).filter(
    (candidate: any) =>
      candidate.protocols?.includes(
        transport === "modbus_rtu_tcp" ? "modbus_rtu" : "modbus_tcp",
      ),
  );
  async function scan(e: React.FormEvent) {
    e.preventDefault();
    setScanning(true);
    setError("");
    setResult(null);
    setSelected(null);
    try {
      const ports = form.ports
        .split(",")
        .map((value) => Number(value.trim()))
        .filter(Number.isFinite);
      setResult(
        await api("/discovery/modbus", token, {
          method: "POST",
          body: JSON.stringify({ ...form, ports, probe_address: 0 }),
        }),
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setScanning(false);
    }
  }
  function prepare(item: any) {
    const candidate = item.profile_candidates?.find((entry: any) =>
      entry.protocols?.includes("modbus_tcp"),
    );
    setSelected(item);
    setTransport("modbus_tcp");
    setProfileId(candidate?.profile_id || "");
    setDeviceName(
      [item.identity?.vendor, item.identity?.model].filter(Boolean).join(" ") ||
        `Dispositivo ${item.host} · ID ${item.unit_id}`,
    );
  }
  async function install() {
    if (!selected || !profileId) return;
    setInstalling(true);
    setError("");
    try {
      await api("/discovery/modbus/install", token, {
        method: "POST",
        body: JSON.stringify({
          host: selected.host,
          port: selected.port,
          unit_id: selected.unit_id,
          profile_id: profileId,
          device_name: deviceName,
          transport,
        }),
      });
      setInstalled([
        ...installed,
        `${selected.host}:${selected.port}:${selected.unit_id}`,
      ]);
      setSelected(null);
      await onInstalled();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setInstalling(false);
    }
  }
  return (
    <div className="discovery-overlay" role="dialog" aria-modal="true">
      <section className="discovery-shell">
        <header className="discovery-head">
          <div className="discovery-brand">
            <span>
              <Radar />
            </span>
            <div>
              <p>NETWORK DISCOVERY</p>
              <h2>Trova dispositivi Modbus</h2>
              <small>
                Scansione guidata, read-only e limitata alla rete industriale.
              </small>
            </div>
          </div>
          <button onClick={onClose} aria-label="Chiudi">
            <X />
          </button>
        </header>
        <div className="discovery-body">
          <aside>
            <div className="discovery-step active">
              <span>1</span>
              <div>
                <b>Definisci la rete</b>
                <small>Subnet, porte e indirizzi slave</small>
              </div>
            </div>
            <div className={`discovery-step ${result ? "active" : ""}`}>
              <span>2</span>
              <div>
                <b>Esamina i risultati</b>
                <small>Gateway e Unit ID che rispondono</small>
              </div>
            </div>
            <div className={`discovery-step ${selected ? "active" : ""}`}>
              <span>3</span>
              <div>
                <b>Conferma il modello</b>
                <small>Verifica sempre la targhetta</small>
              </div>
            </div>
            <div className="discovery-safety">
              <ShieldCheck />
              <b>Discovery sicura</b>
              <p>
                Solo reti private, massimo 256 host. Non vengono scritti
                registri e nulla viene installato senza conferma.
              </p>
            </div>
          </aside>
          <main>
            <form className="scan-config" onSubmit={scan}>
              <label>
                <span>Rete da analizzare</span>
                <div>
                  <Network />
                  <input
                    value={form.network}
                    onChange={(e) =>
                      setForm({ ...form, network: e.target.value })
                    }
                    placeholder="192.168.2.0/24"
                    required
                  />
                </div>
                <small>
                  Puoi usare `/32` per provare un singolo indirizzo.
                </small>
              </label>
              <label>
                <span>Porte TCP</span>
                <div>
                  <Router />
                  <input
                    value={form.ports}
                    onChange={(e) =>
                      setForm({ ...form, ports: e.target.value })
                    }
                    placeholder="502, 5020"
                    required
                  />
                </div>
                <small>Separate da virgola, massimo quattro.</small>
              </label>
              <label>
                <span>Unit ID iniziale</span>
                <input
                  type="number"
                  min="0"
                  max="247"
                  value={form.unit_from}
                  onChange={(e) =>
                    setForm({ ...form, unit_from: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                <span>Unit ID finale</span>
                <input
                  type="number"
                  min="0"
                  max="247"
                  value={form.unit_to}
                  onChange={(e) =>
                    setForm({ ...form, unit_to: Number(e.target.value) })
                  }
                />
              </label>
              <button disabled={scanning}>
                {scanning ? <LoaderCircle className="spin" /> : <Search />}
                {scanning ? "Ricerca in corso…" : "Avvia ricerca"}
              </button>
            </form>
            {error && <div className="discovery-error">{error}</div>}
            {scanning && (
              <div className="radar-stage">
                <div className="radar">
                  <i />
                  <i />
                  <i />
                  <span />
                </div>
                <h3>Sto ascoltando la rete Modbus…</h3>
                <p>
                  Verifico prima le porte aperte, poi interrogo gli Unit ID in
                  sola lettura.
                </p>
              </div>
            )}
            {result && !scanning && (
              <>
                <div className="scan-summary">
                  <span>
                    <b>{result.devices_found}</b> dispositivi
                  </span>
                  <span>
                    <b>{result.endpoints.length}</b> endpoint TCP
                  </span>
                  <span>
                    <b>{result.hosts_scanned}</b> host verificati
                  </span>
                  <em>
                    {(result.elapsed_ms / 1000).toLocaleString("it-IT", {
                      maximumFractionDigits: 1,
                    })}{" "}
                    s
                  </em>
                </div>
                {result.endpoints_skipped > 0 && (
                  <div className="discovery-error">
                    Trovati troppi endpoint aperti: {result.endpoints_skipped}{" "}
                    non approfonditi. Restringi la subnet o le porte.
                  </div>
                )}
                {!devices.length ? (
                  <div className="discovery-empty">
                    <Radar />
                    <h3>Nessuno slave Modbus ha risposto</h3>
                    <p>
                      Controlla subnet, porta, firewall e intervallo Unit ID. Un
                      endpoint TCP aperto può non essere un server Modbus.
                    </p>
                    {result.endpoints?.length > 0 && (
                      <small>
                        {result.endpoints.length} porte TCP aperte senza
                        risposta Modbus valida.
                      </small>
                    )}
                  </div>
                ) : (
                  <div className="found-list">
                    {devices.map((item: any) => {
                      const key = `${item.host}:${item.port}:${item.unit_id}`,
                        top = item.profile_candidates?.[0],
                        done =
                          item.already_configured || installed.includes(key);
                      return (
                        <article
                          key={key}
                          className={
                            selected &&
                            key ===
                              `${selected.host}:${selected.port}:${selected.unit_id}`
                              ? "selected"
                              : ""
                          }
                        >
                          <span className="found-icon">
                            <Zap />
                          </span>
                          <div className="found-main">
                            <div>
                              <b>
                                {item.identity?.model ||
                                  item.identity?.product_code ||
                                  "Dispositivo Modbus"}
                              </b>
                              <em>
                                {item.host}:{item.port} · Unit ID {item.unit_id}
                              </em>
                            </div>
                            <small>
                              {item.identity?.vendor
                                ? `${item.identity.vendor}${item.identity.revision ? ` · FW ${item.identity.revision}` : ""}`
                                : "Identità non pubblicata dal dispositivo"}
                            </small>
                            {top && (
                              <p>
                                <Sparkles /> Suggerito: {top.manufacturer}{" "}
                                {top.model} · confidenza{" "}
                                {Math.round(top.confidence * 100)}%
                              </p>
                            )}
                          </div>
                          {done ? (
                            <span className="already">
                              <CheckCircle2 />
                              Installato
                            </span>
                          ) : (
                            <button onClick={() => prepare(item)}>
                              Configura
                              <ChevronRight />
                            </button>
                          )}
                        </article>
                      );
                    })}
                  </div>
                )}
              </>
            )}
            {selected && (
              <div className="install-drawer">
                <header>
                  <div>
                    <p>CONFERMA INSTALLAZIONE</p>
                    <h3>
                      {selected.host}:{selected.port} · Unit ID{" "}
                      {selected.unit_id}
                    </h3>
                  </div>
                  <button onClick={() => setSelected(null)}>
                    <X />
                  </button>
                </header>
                <div>
                  <div className="discovery-transport">
                    <span>Tipo di collegamento rilevato</span>
                    <div>
                      <button
                        className={transport === "modbus_tcp" ? "active" : ""}
                        onClick={() => {
                          setTransport("modbus_tcp");
                          setProfileId("");
                        }}
                      >
                        <b>TCP diretto</b>
                        <small>
                          Un IP per dispositivo · nessuno Unit ID visibile
                        </small>
                      </button>
                      <button
                        className={
                          transport === "modbus_rtu_tcp" ? "active" : ""
                        }
                        onClick={() => {
                          setTransport("modbus_rtu_tcp");
                          setProfileId("");
                        }}
                      >
                        <b>RTU-over-TCP</b>
                        <small>
                          Gateway condiviso · più dispositivi per Unit ID
                        </small>
                      </button>
                    </div>
                  </div>
                  <label>
                    Nome nell’impianto
                    <input
                      value={deviceName}
                      onChange={(e) => setDeviceName(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Modello / profilo
                    <select
                      value={profileId}
                      onChange={(e) => setProfileId(e.target.value)}
                    >
                      <option value="">
                        Seleziona il modello dalla targhetta…
                      </option>
                      {compatibleCandidates.map((candidate: any) => (
                        <option
                          key={candidate.profile_id}
                          value={candidate.profile_id}
                        >
                          {category(candidate.category)} ·{" "}
                          {candidate.manufacturer} {candidate.model} ·{" "}
                          {Math.round(candidate.confidence * 100)}%
                        </option>
                      ))}
                    </select>
                  </label>
                  <p>
                    <ShieldCheck /> Il riconoscimento automatico non sostituisce
                    la verifica di modello, variante di comunicazione e
                    firmware.
                  </p>
                  <button
                    onClick={() => void install()}
                    disabled={installing || !profileId || !deviceName}
                  >
                    {installing ? (
                      <LoaderCircle className="spin" />
                    ) : (
                      <CheckCircle2 />
                    )}
                    {installing ? "Installazione…" : "Aggiungi all’impianto"}
                  </button>
                </div>
              </div>
            )}
          </main>
        </div>
      </section>
    </div>
  );
}
