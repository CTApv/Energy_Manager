import { Cable, CheckCircle2, EthernetPort, Network, Pencil, Plus, Radar, RefreshCw, Save, Trash2, Usb, Wifi, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ModbusDiscovery } from './modbus-discovery'
import './communications-center.css'

const apiBase=import.meta.env.VITE_API_URL||'/api'
async function api(path:string,token:string,options:RequestInit={}){const response=await fetch(`${apiBase}${path}`,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`}});if(!response.ok)throw new Error((await response.json().catch(()=>({}))).detail||'Operazione non riuscita');return response.json()}
const blank={name:'',kind:'modbus_tcp',host:'192.168.2.108',port:502,serial_port:'/dev/ttyUSB0',baud_rate:9600,parity:'N',stop_bits:1,byte_size:8,timeout:2,retry:1}

export function CommunicationsCenter({token,onPlantChanged}:{token:string,onPlantChanged?:()=>void}){
 const [tab,setTab]=useState('channels'),[connections,setConnections]=useState<any[]>([]),[system,setSystem]=useState<any>(null),[form,setForm]=useState<any>(blank),[editing,setEditing]=useState(''),[discovery,setDiscovery]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[networkEdit,setNetworkEdit]=useState<any>(null)
 const load=async()=>{setError('');try{const [c,s]=await Promise.all([api('/connections',token),api('/system/overview',token)]);setConnections(c);setSystem(s)}catch(e:any){setError(e.message)}}
 useEffect(()=>{void load()},[token])
 const notify=(text:string)=>{setMessage(text);setTimeout(()=>setMessage(''),3500)}
 async function saveConnection(e:React.FormEvent){e.preventDefault();const config=form.kind==='modbus_tcp'?{host:form.host,port:Number(form.port),timeout:Number(form.timeout),retry:Number(form.retry)}:{port:form.serial_port,baud_rate:Number(form.baud_rate),parity:form.parity,stop_bits:Number(form.stop_bits),byte_size:Number(form.byte_size),timeout:Number(form.timeout),retry:Number(form.retry)};try{await api(editing?`/connections/${editing}`:'/connections',token,{method:editing?'PUT':'POST',body:JSON.stringify({name:form.name,kind:form.kind,config})});notify(editing?'Canale aggiornato':'Canale aggiunto');setEditing('');setForm(blank);await load()}catch(e:any){setError(e.message)}}
 function edit(c:any){setEditing(c.id);setForm({name:c.name,kind:c.kind,host:c.config.host||'',port:c.config.port||502,serial_port:c.config.port||'/dev/ttyUSB0',baud_rate:c.config.baud_rate||9600,parity:c.config.parity||'N',stop_bits:c.config.stop_bits||1,byte_size:c.config.byte_size||8,timeout:c.config.timeout??2,retry:c.config.retry??1})}
 async function remove(c:any){if(!window.confirm(`Rimuovere il canale “${c.name}”? L’operazione è consentita solo se non contiene dispositivi.`))return;try{await api(`/connections/${c.id}`,token,{method:'DELETE'});notify('Canale rimosso');await load()}catch(e:any){setError(e.message)}}
 function startNetwork(item:any){const configured=item.configured||{};const ipv4=item.addresses?.find((x:any)=>x.family==='inet');setNetworkEdit({name:item.name,mode:configured.mode||'dhcp',address:configured.address||ipv4?.address||'',prefix:configured.prefix||ipv4?.prefix||24,gateway:configured.gateway||'',dns:(configured.dns||[]).join(', ')})}
 async function saveNetwork(e:React.FormEvent){e.preventDefault();try{const payload={mode:networkEdit.mode,address:networkEdit.mode==='static'?networkEdit.address:'',prefix:Number(networkEdit.prefix),gateway:networkEdit.mode==='static'?networkEdit.gateway:'',dns:networkEdit.mode==='static'?networkEdit.dns.split(',').map((x:string)=>x.trim()).filter(Boolean):[]};const result=await api(`/system/network/${encodeURIComponent(networkEdit.name)}`,token,{method:'PUT',body:JSON.stringify(payload)});notify(result.message);setNetworkEdit(null);await load()}catch(e:any){setError(e.message)}}
 return <div className="communications"><header className="comm-head"><div><p>COMMISSIONING · CONNETTIVITÀ</p><h1>Comunicazioni</h1><span>Configura prima l’Edge, poi i canali industriali. Ogni livello resta separato e leggibile.</span></div><button className="primary-button" onClick={()=>setDiscovery(true)}><Radar/>Ricerca Modbus</button></header>{message&&<div className="notice"><CheckCircle2/>{message}</div>}{error&&<div className="alert">{error}</div>}<nav className="section-tabs"><button className={tab==='channels'?'active':''} onClick={()=>setTab('channels')}><Cable/>Canali industriali</button><button className={tab==='network'?'active':''} onClick={()=>setTab('network')}><Network/>Rete Edge</button><button className={tab==='serial'?'active':''} onClick={()=>setTab('serial')}><Usb/>Porte seriali</button></nav>
 {tab==='channels'&&<div className="comm-grid">
  <section className="panel">
   <header><h2>Canali configurati</h2><button className="icon-button compact" onClick={load}><RefreshCw/>Aggiorna</button></header>
   <div className="channel-list">
    {connections.map(c=><article key={c.id}>
     <span className="channel-icon">{c.kind==='modbus_tcp'?<EthernetPort/>:<Usb/>}</span>
     <div><b>{c.name}</b><small>{c.kind==='modbus_tcp'?`${c.config.host}:${c.config.port}`:`${c.config.port} · ${c.config.baud_rate} baud · ${c.config.parity}${c.config.byte_size}${c.config.stop_bits}`}</small></div>
     <i className={`health-dot ${c.status}`}/><button onClick={()=>edit(c)} title="Modifica"><Pencil/></button><button className="remove" onClick={()=>remove(c)} title="Rimuovi"><Trash2/></button>
    </article>)}
    {!connections.length&&<div className="empty">Nessun canale configurato</div>}
   </div>
  </section>
  <section className="panel">
   <header><h2>{editing?'Modifica canale':'Nuovo canale'}</h2>{editing&&<button onClick={()=>{setEditing('');setForm(blank)}}><X/></button>}</header>
   <form className="form-grid" onSubmit={saveConnection}>
    <label className="wide">Nome leggibile<input value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="Bus contatori quadro generale" required/></label>
    <label className="wide">Tipo<select value={form.kind} onChange={e=>setForm({...form,kind:e.target.value})}><option value="modbus_tcp">Modbus TCP / Ethernet</option><option value="modbus_rtu">Modbus RTU / RS485</option></select></label>
    {form.kind==='modbus_tcp'?<>
     <label>Indirizzo dispositivo<input value={form.host} onChange={e=>setForm({...form,host:e.target.value})} required/></label>
     <label>Porta TCP<input type="number" value={form.port} onChange={e=>setForm({...form,port:e.target.value})}/></label>
    </>:<>
     <label className="wide">Porta COM<select value={form.serial_port} onChange={e=>setForm({...form,serial_port:e.target.value})}><option value={form.serial_port}>{form.serial_port}</option>{system?.serial_ports?.filter((p:any)=>p.path!==form.serial_port).map((p:any)=><option key={p.path} value={p.path}>{p.path}</option>)}</select></label>
     <label>Velocità<select value={form.baud_rate} onChange={e=>setForm({...form,baud_rate:e.target.value})}>{[9600,19200,38400,57600,115200].map(x=><option key={x} value={x}>{x}</option>)}</select></label>
     <label>Formato<select value={`${form.parity}${form.byte_size}${form.stop_bits}`} onChange={e=>setForm({...form,parity:e.target.value[0],byte_size:Number(e.target.value[1]),stop_bits:Number(e.target.value[2])})}><option value="N81">8N1</option><option value="E81">8E1</option><option value="O81">8O1</option><option value="N82">8N2</option></select></label>
    </>}
    <label>Timeout (s)<input type="number" min="0.1" max="30" step="0.1" value={form.timeout} onChange={e=>setForm({...form,timeout:e.target.value})}/></label>
    <label>Retry<input type="number" min="0" max="5" value={form.retry} onChange={e=>setForm({...form,retry:e.target.value})}/></label>
    <button className="primary-button wide"><Save/>{editing?'Salva modifiche':'Crea canale'}</button>
   </form>
  </section>
 </div>}
 {tab==='network'&&<div className="network-layout"><div className="network-warning"><Wifi/><span><b>Evita di perdere l’accesso all’Edge</b><small>Il profilo viene salvato e marcato “da applicare”. L’applicazione sull’host è intenzionalmente separata dalla dashboard.</small></span></div><div className="interface-grid">{system?.interfaces?.map((item:any)=><article key={item.name}><header><span><Network/></span><div><b>{item.name}</b><small>{item.mac||'MAC non disponibile'}</small></div><i className={`health-dot ${item.state}`}/></header><div className="address-list">{item.addresses?.map((a:any)=><code key={`${a.family}-${a.address}`}>{a.address}/{a.prefix}</code>)}{!item.addresses?.length&&<em>Nessun indirizzo</em>}</div><footer><span>{item.configured?.pending_apply?'Modifica in attesa':'Configurazione rilevata'}</span><button onClick={()=>startNetwork(item)}><Pencil/>Configura</button></footer></article>)}</div>{networkEdit&&<section className="panel network-editor"><header><h2>Scheda {networkEdit.name}</h2><button onClick={()=>setNetworkEdit(null)}><X/></button></header><form className="form-grid" onSubmit={saveNetwork}><label className="wide">Assegnazione indirizzo<select value={networkEdit.mode} onChange={e=>setNetworkEdit({...networkEdit,mode:e.target.value})}><option value="dhcp">Automatica (DHCP)</option><option value="static">Manuale (IP statico)</option></select></label>{networkEdit.mode==='static'&&<><label>Indirizzo IPv4<input value={networkEdit.address} onChange={e=>setNetworkEdit({...networkEdit,address:e.target.value})} required/></label><label>Prefisso<input type="number" min="1" max="32" value={networkEdit.prefix} onChange={e=>setNetworkEdit({...networkEdit,prefix:e.target.value})}/></label><label>Gateway<input value={networkEdit.gateway} onChange={e=>setNetworkEdit({...networkEdit,gateway:e.target.value})}/></label><label>DNS (separati da virgola)<input value={networkEdit.dns} onChange={e=>setNetworkEdit({...networkEdit,dns:e.target.value})}/></label></>}<button className="primary-button wide"><Save/>Salva profilo di rete</button></form></section>}</div>}
 {tab==='serial'&&<div className="serial-grid">{system?.serial_ports?.map((p:any)=><article><Usb/><div><b>{p.path}</b><small>{p.available?'Disponibile al servizio Edge':'Non accessibile dal container'}</small></div><span>{connections.filter(c=>c.kind==='modbus_rtu'&&c.config.port===p.path).length} canali</span></article>)}{!system?.serial_ports?.length&&<div className="panel empty-state"><Usb/><h2>Nessuna porta seriale rilevata</h2><p>Collega l’adattatore USB/RS485 e rendilo disponibile al container Edge. Le porte appariranno qui automaticamente.</p><code>docker compose -f docker-compose.edge.yml up -d</code></div>}</div>}
 {discovery&&<ModbusDiscovery token={token} onClose={()=>setDiscovery(false)} onInstalled={async()=>{await load();onPlantChanged?.();notify('Dispositivo trovato e installato')}}/>}</div>
}
