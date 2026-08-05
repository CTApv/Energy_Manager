import { useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Cable,
  CheckCircle2,
  ChevronRight,
  Factory,
  LoaderCircle,
  MapPin,
  Search,
  Server,
  ShieldCheck,
  X,
} from "lucide-react";
import "./device-provisioning-transport.css";

const apiBase = import.meta.env.VITE_API_URL || "/api";

async function api(path: string, token: string, options: RequestInit = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    throw new Error(
      (await response.json().catch(() => ({}))).detail ||
        "Operazione non riuscita",
    );
  }
  return response.json();
}

const categoryLabels: Record<string, string> = {
  multimeter: "Multimetro",
  pv_inverter: "Inverter fotovoltaico",
  battery_storage: "Sistema di accumulo",
  ev_charger: "Stazione di ricarica EV",
  environmental_sensor: "Sensore ambientale",
};

const assetCategory: Record<string, string> = {
  multimeter: "meter",
  pv_inverter: "solar",
  battery_storage: "storage",
  ev_charger: "ev",
  environmental_sensor: "service",
};

const preferredKeys: Record<string, string[]> = {
  multimeter: [
    "electrical.active_power.total",
    "electrical.energy.import_total",
  ],
  pv_inverter: ["pv.power.ac_total", "electrical.active_power.total"],
  battery_storage: ["storage.power.active", "storage.soc"],
  ev_charger: ["ev.power.active", "electrical.active_power.total"],
  environmental_sensor: ["environment.temperature"],
};

type Props = {
  token: string;
  profiles: any[];
  connections: any[];
  assets: any[];
  onClose: () => void;
  onCreated: (openTree: boolean) => Promise<void>;
};

export function DeviceProvisioningWizard({
  token,
  profiles,
  connections,
  assets,
  onClose,
  onCreated,
}: Props) {
  const [step, setStep] = useState(0);
  const [query, setQuery] = useState("");
  const [profileId, setProfileId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [name, setName] = useState("");
  const [unitId, setUnitId] = useState(1);
  const [host, setHost] = useState("");
  const [tcpPort, setTcpPort] = useState(502);
  const [placementMode, setPlacementMode] = useState<"existing" | "new">(
    assets.length ? "existing" : "new",
  );
  const [assetId, setAssetId] = useState(assets[0]?.id || "");
  const [assetName, setAssetName] = useState("");
  const [parentId, setParentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pollWarning, setPollWarning] = useState("");

  const installableProfiles = profiles.filter(
    (item) => !item.definition?.driver?.template,
  );
  const profile = installableProfiles.find((item) => item.id === profileId);
  const definition = profile?.definition || {};
  const connection = connections.find((item) => item.id === connectionId);
  const compatibleConnections = connections.filter((item) => {
    const protocol = item.kind === "modbus_rtu_tcp" ? "modbus_rtu" : item.kind;
    return definition.protocols?.includes(protocol);
  });
  const filteredProfiles = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("it");
    if (!needle) return installableProfiles;
    return installableProfiles.filter((item) => {
      const value = `${item.definition?.manufacturer || ""} ${item.definition?.model || ""} ${item.definition?.family || ""} ${categoryLabels[item.definition?.category] || item.definition?.category || ""}`;
      return value.toLocaleLowerCase("it").includes(needle);
    });
  }, [profiles, query]);
  const measurementKeys = [
    ...(definition.points || []),
    ...(definition.derived_points || []),
  ].map((point: any) => point.key);
  const measurementKey =
    (preferredKeys[definition.category] || []).find((key) =>
      measurementKeys.includes(key),
    ) || measurementKeys[0];

  function chooseProfile(item: any) {
    setProfileId(item.id);
    setConnectionId("");
    if (!name) setName(item.definition?.model || "");
    if (!assetName) setAssetName(item.definition?.model || "");
  }

  function next() {
    setError("");
    if (step === 0 && !profileId)
      return setError("Seleziona il modello dalla targhetta.");
    if (
      step === 1 &&
      (!connectionId ||
        !name.trim() ||
        (connection?.kind === "modbus_tcp" && !host.trim()))
    )
      return setError("Indica connessione e nome del dispositivo.");
    if (
      step === 2 &&
      ((placementMode === "existing" && !assetId) ||
        (placementMode === "new" && !assetName.trim()))
    )
      return setError("Scegli o crea la posizione nell’albero energetico.");
    setStep((value) => Math.min(3, value + 1));
  }

  async function install() {
    setBusy(true);
    setError("");
    try {
      const result = await api("/provisioning/devices", token, {
        method: "POST",
        body: JSON.stringify({
          device: {
            connection_id: connectionId,
            profile_id: profileId,
            name: name.trim(),
            unit_id: connection?.kind === "modbus_tcp" ? null : Number(unitId),
            config:
              connection?.kind === "modbus_tcp"
                ? { host: host.trim(), port: Number(tcpPort) }
                : {},
          },
          placement:
            placementMode === "existing"
              ? { asset_id: assetId }
              : {
                  name: assetName.trim(),
                  parent_id: parentId || null,
                  category: assetCategory[definition.category] || "asset",
                },
          measurement_key: measurementKey,
        }),
      });
      try {
        await api(`/devices/${result.device.id}/poll`, token, {
          method: "POST",
        });
      } catch (pollError: any) {
        setPollWarning(
          `Installazione completata, ma il primo dato non è arrivato: ${pollError.message}`,
        );
      }
      setStep(4);
    } catch (installError: any) {
      setError(installError.message);
    } finally {
      setBusy(false);
    }
  }

  const steps = ["Modello", "Comunicazione", "Posizione", "Verifica"];
  return (
    <div className="wizard-backdrop" role="dialog" aria-modal="true">
      <section className="device-wizard">
        <header>
          <div>
            <p>COMMISSIONING GUIDATO</p>
            <h2>
              {step === 4
                ? "Dispositivo installato"
                : "Aggiungi un dispositivo"}
            </h2>
            <span>
              Il dispositivo viene collocato subito nel suo punto
              dell’ecosistema.
            </span>
          </div>
          <button onClick={onClose} aria-label="Chiudi">
            <X />
          </button>
        </header>

        {step < 4 && (
          <nav className="wizard-steps" aria-label="Avanzamento commissioning">
            {steps.map((label, index) => (
              <button
                key={label}
                className={
                  index === step ? "active" : index < step ? "done" : ""
                }
                onClick={() => index < step && setStep(index)}
                disabled={index > step}
              >
                <span>{index < step ? <CheckCircle2 /> : index + 1}</span>
                {label}
              </button>
            ))}
          </nav>
        )}

        <div className="wizard-body">
          {step === 0 && (
            <>
              <div className="wizard-title">
                <Server />
                <div>
                  <h3>Che cosa stai installando?</h3>
                  <p>
                    Leggi produttore e modello dalla targhetta. Il protocollo
                    verrà filtrato automaticamente.
                  </p>
                </div>
              </div>
              <label className="driver-search">
                <Search />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Cerca produttore, modello o categoria…"
                  autoFocus
                />
              </label>
              <div className="driver-choice-grid">
                {filteredProfiles.map((item) => (
                  <button
                    key={item.id}
                    className={profileId === item.id ? "selected" : ""}
                    onClick={() => chooseProfile(item)}
                  >
                    <span className="driver-category">
                      {categoryLabels[item.definition?.category] ||
                        item.definition?.category}
                    </span>
                    <b>{item.definition?.manufacturer}</b>
                    <strong>{item.definition?.model}</strong>
                    <small>
                      {item.definition?.family || "Driver dedicato"}
                    </small>
                    <em>
                      {(item.definition?.points?.length || 0) +
                        (item.definition?.derived_points?.length || 0)}{" "}
                      misure
                    </em>
                  </button>
                ))}
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <div className="wizard-title">
                <Cable />
                <div>
                  <h3>Come comunica?</h3>
                  <p>
                    Sono mostrati soltanto i canali compatibili con il driver
                    scelto.
                  </p>
                </div>
              </div>
              {!compatibleConnections.length ? (
                <div className="wizard-blocker">
                  <Cable />
                  <b>Nessun canale compatibile</b>
                  <p>
                    Chiudi la procedura, configura Modbus TCP o RTU in
                    Comunicazioni e riprendi da qui.
                  </p>
                </div>
              ) : (
                <div className="connection-choice">
                  {compatibleConnections.map((item) => (
                    <button
                      key={item.id}
                      className={connectionId === item.id ? "selected" : ""}
                      onClick={() => {
                        setConnectionId(item.id);
                        if (item.kind === "modbus_tcp")
                          setTcpPort(Number(item.config?.port || 502));
                      }}
                    >
                      <Cable />
                      <span>
                        <b>{item.name}</b>
                        <small>
                          {item.kind === "modbus_tcp"
                            ? `IP dedicato per dispositivo · porta ${item.config?.port || 502}`
                            : item.kind === "modbus_rtu_tcp"
                              ? `Gateway ${item.config?.host}:${item.config?.port}`
                              : `${item.config?.port} · ${item.config?.baud_rate} baud`}
                        </small>
                      </span>
                      <i />
                    </button>
                  ))}
                </div>
              )}
              <div className="wizard-fields">
                <label>
                  Nome nell’ecosistema
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Contatore generale"
                  />
                </label>
                {connection?.kind === "modbus_tcp" ? (
                  <>
                    <label>
                      IP o hostname del dispositivo
                      <input
                        value={host}
                        onChange={(event) => setHost(event.target.value)}
                        placeholder="192.168.2.108"
                      />
                    </label>
                    <label>
                      Porta TCP
                      <input
                        type="number"
                        min="1"
                        max="65535"
                        value={tcpPort}
                        onChange={(event) =>
                          setTcpPort(Number(event.target.value))
                        }
                      />
                    </label>
                    <div className="tcp-address-note">
                      <ShieldCheck />
                      <span>
                        <b>TCP diretto: nessuno Unit ID da configurare</b>
                        <small>
                          L'indirizzo identifica questo dispositivo. Il driver
                          gestisce internamente il valore di protocollo.
                        </small>
                      </span>
                    </div>
                  </>
                ) : (
                  <label>
                    Slave / Unit ID
                    <input
                      type="number"
                      min="1"
                      max="247"
                      value={unitId}
                      onChange={(event) =>
                        setUnitId(Number(event.target.value))
                      }
                    />
                  </label>
                )}
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <div className="wizard-title">
                <MapPin />
                <div>
                  <h3>Dove misura?</h3>
                  <p>
                    Questa posizione determina il ramo monte/valle e i totali
                    mostrati in dashboard.
                  </p>
                </div>
              </div>
              <div className="placement-toggle">
                <button
                  className={placementMode === "existing" ? "active" : ""}
                  onClick={() => setPlacementMode("existing")}
                  disabled={!assets.length}
                >
                  <Factory />
                  Nodo esistente
                </button>
                <button
                  className={placementMode === "new" ? "active" : ""}
                  onClick={() => setPlacementMode("new")}
                >
                  <MapPin />
                  Nuovo nodo
                </button>
              </div>
              {placementMode === "existing" ? (
                <label className="wizard-select">
                  Posizione nell’albero
                  <select
                    value={assetId}
                    onChange={(event) => setAssetId(event.target.value)}
                  >
                    <option value="">Seleziona…</option>
                    {assets.map((item) => (
                      <option value={item.id} key={item.id}>
                        {item.name} · {item.category}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <div className="wizard-fields">
                  <label>
                    Nome del punto energetico
                    <input
                      value={assetName}
                      onChange={(event) => setAssetName(event.target.value)}
                      placeholder="Punto di consegna, Fotovoltaico, Wallbox…"
                    />
                  </label>
                  <label>
                    Nodo superiore
                    <select
                      value={parentId}
                      onChange={(event) => setParentId(event.target.value)}
                    >
                      <option value="">Radice dell’ecosistema</option>
                      {assets.map((item) => (
                        <option value={item.id} key={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
              <div className="primary-measure">
                <ShieldCheck />
                <span>
                  <b>Misura primaria scelta automaticamente</b>
                  <small>
                    {measurementKey || "Nessuna misura compatibile"}
                  </small>
                </span>
              </div>
            </>
          )}
          {step === 3 && (
            <>
              <div className="wizard-title">
                <ShieldCheck />
                <div>
                  <h3>Controlla e installa</h3>
                  <p>
                    Una sola conferma crea dispositivo, posizione e collegamento
                    energetico.
                  </p>
                </div>
              </div>
              <div className="provision-summary">
                <article>
                  <Server />
                  <span>
                    <small>Dispositivo</small>
                    <b>{name}</b>
                    <em>
                      {definition.manufacturer} {definition.model}
                    </em>
                  </span>
                </article>
                <ChevronRight />
                <article>
                  <Cable />
                  <span>
                    <small>Comunicazione</small>
                    <b>{connection?.name}</b>
                    <em>
                      {connection?.kind === "modbus_tcp"
                        ? `${host}:${tcpPort}`
                        : `Unit ID ${unitId}`}
                    </em>
                  </span>
                </article>
                <ChevronRight />
                <article>
                  <MapPin />
                  <span>
                    <small>Posizione</small>
                    <b>
                      {placementMode === "existing"
                        ? assets.find((item) => item.id === assetId)?.name
                        : assetName}
                    </b>
                    <em>{measurementKey}</em>
                  </span>
                </article>
              </div>
            </>
          )}
          {step === 4 && (
            <div className="wizard-success">
              <span>
                <CheckCircle2 />
              </span>
              <h3>{name} è nell’ecosistema energetico</h3>
              <p>
                Driver, comunicazione e posizione sono stati salvati insieme.
              </p>
              {pollWarning ? (
                <div className="wizard-warning">{pollWarning}</div>
              ) : (
                <div className="wizard-live-ok">
                  Primo ciclo di acquisizione completato.
                </div>
              )}
              <div>
                <button
                  className="icon-button"
                  onClick={() => void onCreated(false)}
                >
                  Chiudi
                </button>
                <button
                  className="primary-button"
                  onClick={() => void onCreated(true)}
                >
                  Vedi nell’albero <ArrowRight />
                </button>
              </div>
            </div>
          )}
          {error && <div className="alert wizard-error">{error}</div>}
        </div>

        {step < 4 && (
          <footer>
            <button
              className="icon-button"
              onClick={step ? () => setStep(step - 1) : onClose}
            >
              {step ? (
                <>
                  <ArrowLeft />
                  Indietro
                </>
              ) : (
                "Annulla"
              )}
            </button>
            {step < 3 ? (
              <button className="primary-button" onClick={next}>
                Continua <ArrowRight />
              </button>
            ) : (
              <button
                className="primary-button"
                onClick={() => void install()}
                disabled={busy || !measurementKey}
              >
                {busy ? <LoaderCircle className="spin" /> : <CheckCircle2 />}
                {busy ? "Installazione…" : "Installa e verifica"}
              </button>
            )}
          </footer>
        )}
      </section>
    </div>
  );
}
