import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Boxes,
  Building2,
  CheckCircle2,
  ChevronRight,
  Copy,
  Factory,
  HardDrive,
  KeyRound,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Signal,
  WifiOff,
  X,
} from "lucide-react";
import "./control-room-studio.css";

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
      (await response.json().catch(() => ({ detail: response.statusText })))
        .detail || `Errore ${response.status}`,
    );
  return response.json();
}
const ago = (value?: string) =>
  value
    ? new Intl.RelativeTimeFormat("it", { numeric: "auto" }).format(
        -Math.max(
          1,
          Math.round((Date.now() - new Date(value).getTime()) / 60000),
        ),
        "minute",
      )
    : "Mai";

type Props = { token: string; page: string; role: string };
export function ControlRoomStudio({ token, page, role }: Props) {
  const [portfolio, setPortfolio] = useState<any>({}),
    [tenants, setTenants] = useState<any[]>([]),
    [sites, setSites] = useState<any[]>([]),
    [edges, setEdges] = useState<any[]>([]),
    [selected, setSelected] = useState<any>(null),
    [open, setOpen] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  const [tenantForm, setTenantForm] = useState({ name: "", slug: "" }),
    [siteForm, setSiteForm] = useState({ tenant_id: "", name: "" }),
    [edgeForm, setEdgeForm] = useState({ site_id: "", name: "", hostname: "" }),
    [secret, setSecret] = useState<any>(null);
  const canCreate = ["platform_admin", "technician"].includes(role);
  async function load() {
    setError("");
    try {
      const [p, t, s, e] = await Promise.all([
        api("/control/portfolio", token),
        api("/control/tenants", token),
        api("/control/sites", token),
        api("/control/edges", token),
      ]);
      setPortfolio(p);
      setTenants(t);
      setSites(s);
      setEdges(e);
      setSiteForm((form) => ({
        ...form,
        tenant_id: form.tenant_id || t[0]?.id || "",
      }));
      setEdgeForm((form) => ({
        ...form,
        site_id: form.site_id || s[0]?.id || "",
      }));
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    void load();
  }, [token]);
  async function create(kind: string, event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const form =
        kind === "tenant" ? tenantForm : kind === "site" ? siteForm : edgeForm;
      const result = await api(
        `/control/${kind === "tenant" ? "tenants" : kind === "site" ? "sites" : "edges"}`,
        token,
        { method: "POST", body: JSON.stringify(form) },
      );
      if (kind === "edge") setSecret(result);
      setNotice(
        `${kind === "tenant" ? "Cliente" : kind === "site" ? "Sito" : "Edge"} creato correttamente`,
      );
      setOpen("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function detail(edge: any) {
    try {
      setSelected(await api(`/control/edges/${edge.id}`, token));
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function activation(edge: any) {
    try {
      const result = await api(`/edges/${edge.id}/activation`, token, {
        method: "POST",
      });
      setSecret({ ...result, name: edge.name });
      setNotice("Codice di attivazione generato");
    } catch (e: any) {
      setError(e.message);
    }
  }
  const title =
    {
      dashboard: "Control Room",
      customers: "Clienti",
      sites: "Siti energetici",
      fleet: "Flotta Edge",
      tree: "Gerarchia della flotta",
      activations: "Attivazioni Edge",
    }[page] || "Control Room";
  const subtitle =
    {
      dashboard:
        "Supervisione multi-cliente senza sottrarre autonomia agli Edge",
      customers: "Organizzazioni e perimetri di accesso",
      sites: "Impianti concentrati per cliente",
      fleet: "Salute, release e continuità di sincronizzazione",
      tree: "Cliente → sito → Edge → dispositivi replicati",
      activations: "Onboarding sicuro e credenziali mostrate una sola volta",
    }[page] || "";
  const byTenant = useMemo(
    () =>
      tenants.map((tenant) => ({
        ...tenant,
        sites: sites
          .filter((site) => site.tenant_id === tenant.id)
          .map((site) => ({
            ...site,
            edges: edges.filter((edge) => edge.site_id === site.id),
          })),
      })),
    [tenants, sites, edges],
  );
  return (
    <div className="cr-studio">
      <header className="cr-head">
        <div>
          <p>ENERGY MANAGER · FLEET OPERATIONS</p>
          <h1>{title}</h1>
          <span>{subtitle}</span>
        </div>
        <div>
          <button onClick={() => void load()}>
            <RefreshCw />
            Aggiorna
          </button>
          {canCreate && page === "customers" && (
            <button className="primary" onClick={() => setOpen("tenant")}>
              <Plus />
              Nuovo cliente
            </button>
          )}
          {canCreate && page === "sites" && (
            <button className="primary" onClick={() => setOpen("site")}>
              <Plus />
              Nuovo sito
            </button>
          )}
          {canCreate && page === "fleet" && (
            <button className="primary" onClick={() => setOpen("edge")}>
              <Plus />
              Registra Edge
            </button>
          )}
        </div>
      </header>
      {error && <div className="cr-error">{error}</div>}
      {notice && (
        <div className="cr-notice">
          <CheckCircle2 />
          {notice}
          <button onClick={() => setNotice("")}>
            <X />
          </button>
        </div>
      )}
      {(page === "dashboard" || page === "fleet") && (
        <section className="cr-metrics">
          <article className="green">
            <Building2 />
            <span>
              Clienti<strong>{portfolio.tenants ?? 0}</strong>
              <small>perimetri isolati</small>
            </span>
          </article>
          <article className="blue">
            <Factory />
            <span>
              Siti<strong>{portfolio.sites ?? 0}</strong>
              <small>impianti concentrati</small>
            </span>
          </article>
          <article className="violet">
            <Server />
            <span>
              Edge online
              <strong>
                {portfolio.online_edges ?? 0}/{portfolio.edges ?? 0}
              </strong>
              <small>{portfolio.degraded_edges || 0} degradati</small>
            </span>
          </article>
          <article className="amber">
            <Activity />
            <span>
              Campioni aggregati
              <strong>
                {Number(portfolio.samples_1m || 0).toLocaleString("it-IT")}
              </strong>
              <small>rollup al minuto</small>
            </span>
          </article>
        </section>
      )}
      {page === "dashboard" && (
        <div className="cr-dashboard">
          <section className="cr-panel">
            <header>
              <div>
                <p>FLEET PULSE</p>
                <h2>Stato operativo</h2>
              </div>
              <span>{edges.length} Edge registrati</span>
            </header>
            <EdgeTable edges={edges} onSelect={detail} />
          </section>
          <section className="cr-panel health">
            <header>
              <div>
                <p>PRIORITÀ</p>
                <h2>Continuità del servizio</h2>
              </div>
            </header>
            <div className="health-list">
              <Health
                icon={Signal}
                label="Sincronizzazione"
                value={`${portfolio.online_edges || 0} Edge connessi`}
                ok={(portfolio.online_edges || 0) === (portfolio.edges || 0)}
              />
              <Health
                icon={Boxes}
                label="Inventario"
                value={`${portfolio.devices || 0} dispositivi replicati`}
                ok
              />
              <Health
                icon={HardDrive}
                label="Conservazione"
                value="Raw 30 giorni · rollup 10 anni"
                ok
              />
            </div>
          </section>
        </div>
      )}
      {page === "customers" && (
        <section className="entity-grid">
          {tenants.map((item) => (
            <article key={item.id}>
              <Building2 />
              <div>
                <b>{item.name}</b>
                <small>{item.slug}</small>
              </div>
              <span>
                {sites.filter((site) => site.tenant_id === item.id).length} siti
              </span>
            </article>
          ))}
        </section>
      )}
      {page === "sites" && (
        <section className="entity-grid">
          {sites.map((item) => (
            <article key={item.id}>
              <Factory />
              <div>
                <b>{item.name}</b>
                <small>{item.tenant}</small>
              </div>
              <span>
                {edges.filter((edge) => edge.site_id === item.id).length} Edge
              </span>
            </article>
          ))}
        </section>
      )}
      {page === "fleet" && (
        <section className="cr-panel">
          <header>
            <div>
              <p>EDGE DIRECTORY</p>
              <h2>Nodi registrati</h2>
            </div>
            <span>Commissioning sempre locale</span>
          </header>
          <EdgeTable
            edges={edges}
            onSelect={detail}
            onActivation={canCreate ? activation : undefined}
          />
        </section>
      )}
      {page === "tree" && (
        <section className="fleet-tree">
          {byTenant.map((tenant) => (
            <article key={tenant.id}>
              <header>
                <Building2 />
                <div>
                  <b>{tenant.name}</b>
                  <small>{tenant.sites.length} siti</small>
                </div>
              </header>
              {tenant.sites.map((site: any) => (
                <div className="site-branch" key={site.id}>
                  <span>
                    <ChevronRight />
                    <Factory />
                    <b>{site.name}</b>
                  </span>
                  {site.edges.map((edge: any) => (
                    <button key={edge.id} onClick={() => void detail(edge)}>
                      <i className={edge.status} />
                      <Server />
                      <span>
                        <b>{edge.name}</b>
                        <small>
                          {edge.app_version} · {edge.backlog_count || 0} in coda
                        </small>
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </article>
          ))}
        </section>
      )}
      {page === "activations" && (
        <section className="cr-panel">
          <header>
            <div>
              <p>ZERO-TOUCH ENROLLMENT</p>
              <h2>Edge da attivare</h2>
            </div>
            <span>Codici monouso con scadenza</span>
          </header>
          <div className="activation-list">
            {edges.map((edge) => (
              <article key={edge.id}>
                <ShieldCheck />
                <span>
                  <b>{edge.name}</b>
                  <small>
                    {edge.tenant} · {edge.site}
                  </small>
                </span>
                <button onClick={() => void activation(edge)}>
                  <KeyRound />
                  Genera codice
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
      {open && (
        <div
          className="cr-modal"
          onMouseDown={(e) => e.target === e.currentTarget && setOpen("")}
        >
          <form onSubmit={(e) => void create(open, e)}>
            <header>
              <div>
                <b>
                  {open === "tenant"
                    ? "Nuovo cliente"
                    : open === "site"
                      ? "Nuovo sito"
                      : "Registra un Edge"}
                </b>
                <span>
                  La configurazione dei dispositivi resterà sull’Edge.
                </span>
              </div>
              <button type="button" onClick={() => setOpen("")}>
                <X />
              </button>
            </header>
            {open === "tenant" && (
              <>
                <label>
                  Ragione sociale
                  <input
                    required
                    value={tenantForm.name}
                    onChange={(e) =>
                      setTenantForm({ ...tenantForm, name: e.target.value })
                    }
                  />
                </label>
                <label>
                  Codice cliente
                  <input
                    required
                    pattern="[a-z0-9-]+"
                    value={tenantForm.slug}
                    onChange={(e) =>
                      setTenantForm({
                        ...tenantForm,
                        slug: e.target.value.toLowerCase(),
                      })
                    }
                  />
                </label>
              </>
            )}
            {open === "site" && (
              <>
                <label>
                  Cliente
                  <select
                    required
                    value={siteForm.tenant_id}
                    onChange={(e) =>
                      setSiteForm({ ...siteForm, tenant_id: e.target.value })
                    }
                  >
                    {tenants.map((t) => (
                      <option value={t.id} key={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Nome sito
                  <input
                    required
                    value={siteForm.name}
                    onChange={(e) =>
                      setSiteForm({ ...siteForm, name: e.target.value })
                    }
                  />
                </label>
              </>
            )}
            {open === "edge" && (
              <>
                <label>
                  Sito
                  <select
                    required
                    value={edgeForm.site_id}
                    onChange={(e) =>
                      setEdgeForm({ ...edgeForm, site_id: e.target.value })
                    }
                  >
                    {sites.map((s) => (
                      <option value={s.id} key={s.id}>
                        {s.tenant} · {s.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Nome Edge
                  <input
                    required
                    value={edgeForm.name}
                    onChange={(e) =>
                      setEdgeForm({ ...edgeForm, name: e.target.value })
                    }
                  />
                </label>
                <label>
                  Hostname
                  <input
                    value={edgeForm.hostname}
                    onChange={(e) =>
                      setEdgeForm({ ...edgeForm, hostname: e.target.value })
                    }
                    placeholder="em-edge-001"
                  />
                </label>
              </>
            )}
            <footer>
              <button type="button" onClick={() => setOpen("")}>
                Annulla
              </button>
              <button className="primary" disabled={busy}>
                {busy ? "Salvataggio…" : "Conferma"}
              </button>
            </footer>
          </form>
        </div>
      )}
      {selected && (
        <div
          className="cr-modal"
          onMouseDown={(e) => e.target === e.currentTarget && setSelected(null)}
        >
          <section className="edge-detail">
            <header>
              <div>
                <b>{selected.name}</b>
                <span>
                  {selected.tenant || ""} {selected.site || ""}
                </span>
              </div>
              <button onClick={() => setSelected(null)}>
                <X />
              </button>
            </header>
            <div className="edge-detail-kpis">
              <span>
                Stato<b>{selected.status}</b>
              </span>
              <span>
                Versione<b>{selected.app_version}</b>
              </span>
              <span>
                Backlog<b>{selected.backlog_count || 0}</b>
              </span>
              <span>
                Disco libero<b>{selected.disk_free_percent ?? "—"}%</b>
              </span>
            </div>
            <h3>Dispositivi replicati</h3>
            <div className="remote-devices">
              {selected.devices?.map((device: any) => (
                <article key={device.id}>
                  <i className={device.status} />
                  <span>
                    <b>{device.name}</b>
                    <small>
                      {device.manufacturer} {device.model}
                    </small>
                  </span>
                  <em>{device.category}</em>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
      {secret && (
        <div className="secret-banner">
          <KeyRound />
          <div>
            <b>Credenziale mostrata una sola volta</b>
            <code>{secret.enrollment_token || secret.code}</code>
            <small>Copiala ora e conservala nel secret store dell’Edge.</small>
          </div>
          <button
            onClick={() =>
              navigator.clipboard.writeText(
                secret.enrollment_token || secret.code,
              )
            }
          >
            <Copy />
            Copia
          </button>
          <button onClick={() => setSecret(null)}>
            <X />
          </button>
        </div>
      )}
    </div>
  );
}

function EdgeTable({
  edges,
  onSelect,
  onActivation,
}: {
  edges: any[];
  onSelect: (edge: any) => void;
  onActivation?: (edge: any) => void;
}) {
  return (
    <div className="edge-table">
      <div className="edge-row head">
        <span>Edge</span>
        <span>Cliente / sito</span>
        <span>Release</span>
        <span>Sincronizzazione</span>
        <span>Stato</span>
        <span />
      </div>
      {edges.map((edge) => (
        <div className="edge-row" key={edge.id}>
          <div>
            <i className={edge.status} />
            <span>
              <b>{edge.name}</b>
              <small>{edge.hostname || edge.id}</small>
            </span>
          </div>
          <span>
            {edge.tenant}
            <small>{edge.site}</small>
          </span>
          <code>{edge.app_version || "—"}</code>
          <span>
            {ago(edge.last_sync_at || edge.last_seen_at)}
            <small>{edge.backlog_count || 0} eventi in coda</small>
          </span>
          <em className={edge.status}>{edge.status}</em>
          <div>
            <button onClick={() => onSelect(edge)}>Dettagli</button>
            {onActivation && (
              <button
                onClick={() => onActivation(edge)}
                title="Genera attivazione"
              >
                <KeyRound />
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
function Health({
  icon: Icon,
  label,
  value,
  ok,
}: {
  icon: any;
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <article>
      <span className={ok ? "ok" : "bad"}>
        <Icon />
      </span>
      <div>
        <b>{label}</b>
        <small>{value}</small>
      </div>
      {ok ? <CheckCircle2 /> : <WifiOff />}
    </article>
  );
}
