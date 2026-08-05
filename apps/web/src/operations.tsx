import React, { useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, BatteryCharging, Bell, CarFront, Check, ChevronRight, CircleGauge, Clock3, CloudSun, Factory, Gauge, Network, Radio, RefreshCw, Search, Settings2, ShieldCheck, SlidersHorizontal, Sun, TrendingUp, Wifi, Zap } from 'lucide-react'
import './operations.css'

const apiBase = import.meta.env.VITE_API_URL || '/api'

async function api(path:string, token:string, options:RequestInit={}) {
  const response=await fetch(`${apiBase}${path}`,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,...options.headers}})
  if(!response.ok)throw new Error((await response.json().catch(()=>({detail:response.statusText}))).detail||`Errore ${response.status}`)
  return response.json()
}

const fmt=(value:any,digits=1)=>value===null||value===undefined?'—':Number(value).toLocaleString('it-IT',{maximumFractionDigits:digits})
const time=(value:any)=>value?new Date(value).toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—'
const severityLabel:Record<string,string>={info:'Informativo',warning:'Avviso',high:'Alto',critical:'Critico'}
const conditionLabel:Record<string,string>={measurement_above:'superiore a',measurement_below:'inferiore a',measurement_outside:'fuori intervallo'}

type MetricFamily='power'|'voltage'|'current'|'energy'|'quality'|'frequency'|'thermal'|'solar'|'storage'|'mobility'|'weather'|'state'|'other'
type GaugeSpec={keys:string[],label:string,min?:number,max?:number,tone?:string,family?:MetricFamily}
type DashboardPreset={label:string,eyebrow:string,icon:any,tone:string,gauges:GaugeSpec[],charts:string[][]}

const metricFamilies:Record<MetricFamily,{label:string,description:string,color:string,palette:string[]}>= {
  power:{label:'Potenze',description:'Flussi attivi, reattivi e apparenti',color:'#00a878',palette:['#00a878','#ef9f20','#3b82f6','#e05757']},
  voltage:{label:'Tensioni',description:'Livelli di tensione e bilanciamento delle fasi',color:'#1689e6',palette:['#1689e6','#40a7f4','#75c4ff','#0e6eb8']},
  current:{label:'Correnti',description:'Carico elettrico sulle singole fasi',color:'#7c5ce5',palette:['#7654d8','#9a74ef','#bd9cff','#5735b1']},
  energy:{label:'Energie',description:'Energia prodotta, assorbita e contabilizzata',color:'#dc8a13',palette:['#dc8a13','#f0aa32','#ffc65c','#b86a05']},
  quality:{label:'Qualità della rete',description:'Fattore di potenza, armoniche e squilibri',color:'#d14b7d',palette:['#d14b7d','#ed719e','#a94cba','#ef8f63']},
  frequency:{label:'Frequenza',description:'Stabilità della frequenza di rete',color:'#0c9ca6',palette:['#0c9ca6','#35bdc5','#08777e']},
  thermal:{label:'Temperature',description:'Condizioni termiche e protezione del dispositivo',color:'#db643f',palette:['#db643f','#f18a56','#b7472a']},
  solar:{label:'Risorsa solare',description:'Irraggiamento e prestazione fotovoltaica',color:'#d99308',palette:['#d99308','#f3b62d','#ffd469']},
  storage:{label:'Accumulo',description:'Stato, capacità e disponibilità energetica',color:'#6d55cc',palette:['#6d55cc','#947be7','#b5a2f1']},
  mobility:{label:'Ricarica elettrica',description:'Sessione, connettore e limiti di ricarica',color:'#087cb8',palette:['#087cb8','#31a0d6','#6abce4']},
  weather:{label:'Dati ambientali',description:'Meteo, vento e condizioni del sito',color:'#158a94',palette:['#158a94','#37a9b2','#65c4ca']},
  state:{label:'Stato e diagnostica',description:'Disponibilità, allarmi e stato operativo',color:'#596d65',palette:['#596d65','#7f918a','#a2afa9']},
  other:{label:'Altre misure',description:'Parametri operativi del dispositivo',color:'#547168',palette:['#547168','#789088','#9aacA5']},
}

const metricFamily=(key:string,group=''):MetricFamily=>{
  const probe=`${key} ${group}`.toLowerCase()
  if(/voltage|tensione/.test(probe))return 'voltage'
  if(/current|corrente/.test(probe))return 'current'
  if(/power_factor|cosphi|thd|unbalance|angle|qualit/.test(probe))return 'quality'
  if(/frequency|frequenza/.test(probe))return 'frequency'
  if(/energy|energia|energie/.test(probe))return 'energy'
  if(/power|potenz/.test(probe))return 'power'
  if(/temperature|thermal|termic/.test(probe))return 'thermal'
  if(/irradiance|albedo|soiling|solar|irraggiamento/.test(probe))return 'solar'
  if(/storage|soc|soh|batter|accumulo/.test(probe))return 'storage'
  if(/^ev\.|ricarica|connettore|sessione/.test(probe))return 'mobility'
  if(/environment|meteo|vento|umid|piogg|pression|neve/.test(probe))return 'weather'
  if(/state|status|alarm|diagnostic|stato|allarm/.test(probe))return 'state'
  return 'other'
}
const gaugeFamily=(spec:GaugeSpec,measurement?:any)=>spec.family||metricFamily(measurement?.key||spec.keys[0],measurement?.group)
const familyForKeys=(keys:string[],measurements:any[])=>metricFamily(keys[0]||'',measurements.find(item=>keys.includes(item.key))?.group)
const chartColor=(key:string,index:number)=>{const family=metricFamily(key);const palette=metricFamilies[family].palette;return palette[index%palette.length]}

const dashboardPresets:Record<string,DashboardPreset>={
  multimeter:{label:'Analizzatore di rete',eyebrow:'QUALITÀ E CONSUMI',icon:CircleGauge,tone:'grid',gauges:[
    {keys:['electrical.active_power.total'],label:'Potenza attiva',min:0,tone:'cyan'},
    {keys:['electrical.voltage.l1n','electrical.voltage.l1_n'],label:'Tensione L1',min:0,max:260,tone:'blue'},
    {keys:['electrical.voltage.l2n','electrical.voltage.l2_n'],label:'Tensione L2',min:0,max:260,tone:'blue'},
    {keys:['electrical.voltage.l3n','electrical.voltage.l3_n'],label:'Tensione L3',min:0,max:260,tone:'blue'},
    {keys:['electrical.current.l1'],label:'Corrente L1',min:0,tone:'violet'},
    {keys:['electrical.current.l2'],label:'Corrente L2',min:0,tone:'violet'},
    {keys:['electrical.current.l3'],label:'Corrente L3',min:0,tone:'violet'},
    {keys:['electrical.power_factor.total'],label:'Fattore di potenza',min:0,max:1,tone:'amber'},
    {keys:['electrical.frequency'],label:'Frequenza',min:45,max:55,tone:'violet'},
    {keys:['electrical.thd.voltage.l1'],label:'THD tensione L1',min:0,max:10,tone:'amber'},
  ],charts:[['electrical.active_power.total','electrical.reactive_power.total','electrical.apparent_power.total'],['electrical.voltage.l1n','electrical.voltage.l1_n','electrical.voltage.l2n','electrical.voltage.l2_n','electrical.voltage.l3n','electrical.voltage.l3_n'],['electrical.current.l1','electrical.current.l2','electrical.current.l3'],['electrical.power_factor.l1','electrical.power_factor.l2','electrical.power_factor.l3']]},
  pv_inverter:{label:'Generazione fotovoltaica',eyebrow:'SOLAR PERFORMANCE',icon:Sun,tone:'solar',gauges:[
    {keys:['pv.power.ac_total'],label:'Produzione AC',min:0,tone:'solar'},
    {keys:['pv.inverter.efficiency'],label:'Rendimento',min:0,max:100,tone:'green'},
    {keys:['pv.voltage.dc'],label:'Tensione DC',min:0,max:1200,tone:'blue'},
    {keys:['pv.current.dc'],label:'Corrente DC',min:0,tone:'cyan'},
    {keys:['pv.inverter.temperature'],label:'Temperatura inverter',min:0,max:100,tone:'amber'},
    {keys:['pv.energy.today'],label:'Energia prodotta oggi',min:0,tone:'solar'},
    {keys:['electrical.power_factor.total'],label:'Fattore di potenza',min:0,max:1,tone:'violet'},
  ],charts:[['pv.power.ac_total','pv.power.dc_total'],['pv.voltage.string1','pv.voltage.string2'],['pv.current.string1','pv.current.string2'],['electrical.voltage.l1n','electrical.voltage.l2n','electrical.voltage.l3n']]},
  battery_storage:{label:'Sistema di accumulo',eyebrow:'ENERGY STORAGE',icon:BatteryCharging,tone:'storage',gauges:[
    {keys:['storage.soc'],label:'Stato di carica',min:0,max:100,tone:'violet'},
    {keys:['storage.soh'],label:'Stato di salute',min:0,max:100,tone:'green'},
    {keys:['storage.power.active'],label:'Potenza batteria',tone:'cyan'},
    {keys:['storage.temperature'],label:'Temperatura',min:0,max:70,tone:'amber'},
    {keys:['storage.energy.available'],label:'Energia disponibile',min:0,tone:'green'},
    {keys:['storage.voltage.dc'],label:'Tensione DC',min:0,max:1000,tone:'blue'},
    {keys:['storage.current.dc'],label:'Corrente DC',tone:'violet'},
  ],charts:[['storage.power.active'],['storage.soc'],['storage.voltage.dc'],['storage.temperature','storage.temperature.max','storage.temperature.min']]},
  ev_charger:{label:'Stazione di ricarica',eyebrow:'E-MOBILITY SESSION',icon:CarFront,tone:'ev',gauges:[
    {keys:['ev.power.active'],label:'Potenza di ricarica',min:0,tone:'blue'},
    {keys:['ev.current.limit'],label:'Limite corrente',min:0,max:63,tone:'cyan'},
    {keys:['electrical.current.l1'],label:'Corrente L1',min:0,max:63,tone:'violet'},
    {keys:['electrical.voltage.l1n'],label:'Tensione L1',min:0,max:260,tone:'blue'},
    {keys:['ev.energy.session'],label:'Energia sessione',min:0,tone:'green'},
    {keys:['ev.temperature'],label:'Temperatura interna',min:0,max:80,tone:'amber'},
    {keys:['ev.availability'],label:'Disponibilità',min:0,max:100,tone:'green'},
  ],charts:[['ev.power.active'],['electrical.current.l1','electrical.current.l2','electrical.current.l3'],['electrical.voltage.l1n','electrical.voltage.l2n','electrical.voltage.l3n'],['ev.energy.session']]},
  environmental_sensor:{label:'Stazione meteo e sensori',eyebrow:'ENVIRONMENTAL DATA',icon:CloudSun,tone:'weather',gauges:[
    {keys:['environment.irradiance.poa'],label:'Irraggiamento',min:0,max:1400,tone:'solar'},
    {keys:['environment.temperature.ambient'],label:'Temperatura ambiente',min:-20,max:60,tone:'amber'},
    {keys:['environment.temperature.module'],label:'Temperatura moduli',min:-20,max:100,tone:'violet'},
    {keys:['environment.wind.speed'],label:'Velocità vento',min:0,max:40,tone:'blue'},
    {keys:['environment.humidity.relative'],label:'Umidità relativa',min:0,max:100,tone:'cyan'},
    {keys:['environment.pressure.atmospheric'],label:'Pressione atmosferica',min:950,max:1050,tone:'green'},
    {keys:['environment.wind.direction'],label:'Direzione vento',min:0,max:360,tone:'violet'},
    {keys:['environment.wind.gust'],label:'Raffica',min:0,max:50,tone:'blue'},
  ],charts:[['environment.irradiance.poa','environment.irradiance.ghi'],['environment.temperature.ambient','environment.temperature.module'],['environment.wind.speed','environment.wind.gust'],['environment.humidity.relative']]},
}

const defaultPreset:DashboardPreset={label:'Dispositivo connesso',eyebrow:'LIVE TELEMETRY',icon:Radio,tone:'generic',gauges:[],charts:[]}
const findMeasure=(measurements:any[],keys:string[])=>keys.map(key=>measurements.find(item=>item.key===key)).find(Boolean)

function LiveBadge({online=true,status}:{online?:boolean,status?:string}){const state=status|| (online?'online':'offline');const label=state==='online'?'LIVE':state==='degraded'?'DEGRADATO':'OFFLINE';return <span className={`live-badge ${state}`}><i/>{label}</span>}

function Trend({series}:{series:any[]}){
  const values=series.map(point=>Number(point.value)).filter(Number.isFinite)
  if(values.length<2)return <div className="ops-empty">Il grafico comparirà dopo due campioni validi.</div>
  const min=Math.min(...values),max=Math.max(...values),span=Math.max(max-min,1)
  const line=values.map((value,index)=>`${index*(760/Math.max(values.length-1,1))},${174-((value-min)/span)*132}`).join(' ')
  return <div className="trend"><div className="trend-scale"><span>{fmt(max)} kW</span><span>{fmt((max+min)/2)} kW</span><span>{fmt(min)} kW</span></div><svg viewBox="0 0 760 200" preserveAspectRatio="none" role="img" aria-label="Andamento potenza attiva"><defs><linearGradient id="ops-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#18b981" stopOpacity=".28"/><stop offset="1" stopColor="#18b981" stopOpacity="0"/></linearGradient></defs><line x1="0" y1="42" x2="760" y2="42"/><line x1="0" y1="108" x2="760" y2="108"/><line x1="0" y1="174" x2="760" y2="174"/><polygon points={`0,190 ${line} 760,190`} fill="url(#ops-fill)"/><polyline points={line} fill="none" stroke="#13a974" strokeWidth="3" vectorEffect="non-scaling-stroke"/></svg><div className="trend-time"><span>{time(series[0]?.time)}</span><span>{time(series.at(-1)?.time)}</span></div></div>
}

function RadialGauge({measurement,spec}:{measurement:any,spec:GaugeSpec}){
  const value=Number(measurement?.value),valid=Number.isFinite(value)
  const min=spec.min??0,max=spec.max??Math.max(Math.abs(value)*1.25,1)
  const progress=valid?Math.max(0,Math.min(1,(value-min)/Math.max(max-min,.0001))):0
  const family=gaugeFamily(spec,measurement)
  return <article className={`radial-gauge family-${family} ${measurement?.quality!=='good'?'uncertain':''}`}>
    <div className="gauge-visual">
      <svg viewBox="0 0 132 78" aria-label={`${spec.label}: ${valid?value:'dato non disponibile'}`}>
        <path className="gauge-track" d="M14 66a52 52 0 0 1 104 0" pathLength="100"/>
        <path className="gauge-value" d="M14 66a52 52 0 0 1 104 0" pathLength="100" style={{strokeDasharray:`${progress*100} 100`}}/>
      </svg>
      <div className="gauge-reading"><strong>{valid?fmt(value,Math.abs(value)<10?2:1):'—'}</strong><small>{measurement?.unit||''}</small></div>
    </div>
    <div className="gauge-caption"><span>{spec.label}</span><i className={measurement?.quality==='good'?'good':''}/></div>
    <div className="gauge-range"><span>{fmt(min)}</span><span>{fmt(max)}</span></div>
  </article>
}

function AdaptiveChart({series,measurements,title}:{series:any[],measurements:any[],title:string}){
  const populated=series.filter(item=>item.points?.length>1)
  if(!populated.length)return <div className="adaptive-chart empty"><TrendingUp/><b>{title}</b><span>Il grafico si attiverà dopo due campioni validi.</span></div>
  const values=populated.flatMap(item=>item.points.map((point:any)=>Number(point.avg))).filter(Number.isFinite)
  const min=Math.min(...values),max=Math.max(...values),span=Math.max(max-min,.0001)
  const paths=populated.map((item,index)=>({item,color:chartColor(item.key,index),points:item.points.map((point:any,pointIndex:number)=>`${pointIndex*(720/Math.max(item.points.length-1,1))},${184-((Number(point.avg)-min)/span)*142}`).join(' ')}))
  return <article className="adaptive-chart"><header><div><p>ANDAMENTO</p><h3>{title}</h3></div><span>{populated[0]?.points.length||0} intervalli</span></header><div className="adaptive-chart-body"><div className="chart-y"><span>{fmt(max)}</span><span>{fmt((max+min)/2)}</span><span>{fmt(min)}</span></div><svg viewBox="0 0 720 205" preserveAspectRatio="none"><line x1="0" y1="42" x2="720" y2="42"/><line x1="0" y1="113" x2="720" y2="113"/><line x1="0" y1="184" x2="720" y2="184"/>{paths.map(path=><polyline key={path.item.key} points={path.points} fill="none" stroke={path.color} strokeWidth="3" vectorEffect="non-scaling-stroke"/>)}</svg></div><footer>{paths.map(path=>{const meta=measurements.find(item=>item.key===path.item.key);return <span key={path.item.key}><i style={{background:path.color}}/>{meta?.label||path.item.key}<small>{path.item.unit}</small></span>})}</footer></article>
}

function DeviceLiveCockpit({token,data,query,setQuery}:{token:string,data:any,query:string,setQuery:(value:string)=>void}){
  const device=data.primary_meter,measurements=data.measurements||[]
  const preset=dashboardPresets[device?.category]||defaultPreset,Icon=preset.icon
  const [tab,setTab]=useState<'overview'|'trends'|'telemetry'>('overview'),[hours,setHours]=useState(24),[history,setHistory]=useState<any[]>([]),[historyLoading,setHistoryLoading]=useState(false)
  const configured=useMemo(()=>preset.gauges.map(spec=>({spec,measurement:findMeasure(measurements,spec.keys)})).filter(item=>item.measurement),[measurements,preset])
  const gauges=useMemo(()=>configured.length?configured:measurements.filter((item:any)=>Number.isFinite(Number(item.value))).slice(0,4).map((measurement:any)=>({measurement,spec:{keys:[measurement.key],label:measurement.label,tone:'cyan'} as GaugeSpec})),[configured,measurements])
  const gaugeSections=useMemo(()=>{const result=new Map<MetricFamily,any[]>();gauges.forEach((item:any)=>{const family=gaugeFamily(item.spec,item.measurement);result.set(family,[...(result.get(family)||[]),item])});return Array.from(result.entries())},[gauges])
  const chartGroups=useMemo(()=>preset.charts.map(keys=>keys.filter(key=>measurements.some((item:any)=>item.key===key))).filter(keys=>keys.length),[measurements,preset])
  useEffect(()=>{if(!device?.id||!chartGroups.length){setHistory([]);return}let cancelled=false;setHistoryLoading(true);const keys=Array.from(new Set(chartGroups.flat())).join(',');void api(`/analytics/timeseries?device_id=${encodeURIComponent(device.id)}&hours=${hours}&bucket_minutes=${hours<=6?1:hours<=24?5:60}&measurement_keys=${encodeURIComponent(keys)}`,token).then(result=>{if(!cancelled)setHistory(result.series||[])}).catch(()=>{if(!cancelled)setHistory([])}).finally(()=>{if(!cancelled)setHistoryLoading(false)});return()=>{cancelled=true}},[token,device?.id,hours,chartGroups.map(group=>group.join(',')).join('|')])
  if(!device)return null
  const good=measurements.filter((item:any)=>item.quality==='good').length
  return <section className={`device-cockpit ${preset.tone} ${device.status}`}>
    <header className="cockpit-hero"><div className="cockpit-symbol"><Icon/><span/></div><div className="cockpit-identity"><p>{preset.eyebrow}</p><h2>{device.name}</h2><span>{preset.label} · {device.manufacturer} {device.model}</span></div><div className="cockpit-health"><LiveBadge status={device.status}/><span><b>{good}/{measurements.length}</b> misure valide</span><span><b>{fmt(device.cycle_duration_ms,0)} ms</b> ciclo Edge</span></div></header>
    <nav className="cockpit-tabs" aria-label="Sezioni dashboard dispositivo"><button className={tab==='overview'?'active':''} onClick={()=>setTab('overview')}><Gauge/>Quadro live</button><button className={tab==='trends'?'active':''} onClick={()=>setTab('trends')}><TrendingUp/>Andamenti</button><button className={tab==='telemetry'?'active':''} onClick={()=>setTab('telemetry')}><Radio/>Tutte le misure <em>{measurements.length}</em></button></nav>
    {tab==='overview'&&<><div className="gauge-sections">{gaugeSections.map(([family,items])=>{const meta=metricFamilies[family];return <section className={`gauge-section family-${family}`} key={family}><header><span className="family-mark"><i/></span><div><h3>{meta.label}</h3><p>{meta.description}</p></div><em>{items.length} {items.length===1?'misura':'misure'}</em></header><div className="gauge-deck">{items.map(({measurement,spec}:any)=><RadialGauge key={measurement.key} measurement={measurement} spec={spec}/>)}</div></section>})}</div>{chartGroups[0]&&<div className="cockpit-chart-feature"><AdaptiveChart series={history.filter(item=>chartGroups[0].includes(item.key))} measurements={measurements} title={metricFamilies[familyForKeys(chartGroups[0],measurements)].label}/></div>}</>}
    {tab==='trends'&&<div className="trend-workspace"><div className="trend-controls"><div><p>ORIZZONTE TEMPORALE</p><span>Storico aggregato con soli campioni validi</span></div><nav>{[{v:1,l:'1 ora'},{v:6,l:'6 ore'},{v:24,l:'24 ore'},{v:168,l:'7 giorni'}].map(period=><button key={period.v} className={hours===period.v?'active':''} onClick={()=>setHours(period.v)}>{period.l}</button>)}</nav></div>{historyLoading?<div className="cockpit-loading"><RefreshCw/>Elaborazione storico…</div>:<div className="adaptive-chart-grid">{chartGroups.map(keys=>{const family=familyForKeys(keys,measurements);return <AdaptiveChart key={keys.join()} series={history.filter(item=>keys.includes(item.key))} measurements={measurements} title={metricFamilies[family].label}/>})}</div>}</div>}
    {tab==='telemetry'&&<MeasurementGrid measurements={measurements} query={query} setQuery={setQuery}/>}
  </section>
}

function SummaryCard({label,value,unit,icon:Icon,tone='green',detail}:{label:string,value:any,unit:string,icon:any,tone?:string,detail:string}){return <article className={`ops-kpi ${tone}`}><div><span>{label}</span><Icon/></div><strong>{fmt(value,value&&Math.abs(value)<10?2:1)} <small>{value!==null&&value!==undefined?unit:''}</small></strong><p>{detail}</p></article>}

function MeasurementGrid({measurements,query,setQuery}:{measurements:any[],query:string,setQuery:(value:string)=>void}){
  const groups=useMemo(()=>{const result=new Map<MetricFamily,any[]>();measurements.filter(item=>(item.label+' '+item.key+' '+(item.group||'')).toLowerCase().includes(query.toLowerCase())).forEach(item=>{const family=metricFamily(item.key,item.group);result.set(family,[...(result.get(family)||[]),item])});return Array.from(result.entries())},[measurements,query])
  return <section className="ops-section measurement-catalog"><header><div><p className="ops-eyebrow">TELEMETRIA NORMALIZZATA</p><h2>Dati live per grandezza</h2></div><label className="measure-search"><Search/><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="Cerca misura…" aria-label="Cerca misura"/></label></header>{groups.length?groups.map(([family,items])=>{const meta=metricFamilies[family];return <div className={`measure-group family-${family}`} key={family}><div className="measure-group-title"><span className="family-mark"><i/></span><div><h3>{meta.label}<span>{items.length}</span></h3><p>{meta.description}</p></div></div><div className="measure-grid">{items.map(item=><article className={`family-${family}`} key={item.key}><div><span>{item.label}</span><i className={item.quality==='good'?'good':'bad'} title={item.quality}/></div><strong>{item.display_value||fmt(item.value,Math.abs(item.value)<10?2:1)} <small>{item.unit}</small></strong>{item.display_value&&<em className="raw-state">Codice {fmt(item.value,0)}</em>}<p>{time(item.sample_at)} · {item.quality==='good'?'Dato valido':item.quality}</p></article>)}</div></div>}):<div className="ops-empty">Nessuna misura corrisponde alla ricerca.</div>}</section>
}

function AlarmCenter({token,data,rules,onChanged}:{token:string,data:any,rules:any[],onChanged:()=>void}){
  const measurements=data.measurements||[],selected=data.primary_meter
  const [open,setOpen]=useState(false),[error,setError]=useState(''),[saving,setSaving]=useState(false)
  const [form,setForm]=useState<any>({name:'',measurement_key:'electrical.active_power.total',condition:'above',threshold:100,deadband:2,severity:'warning'})
  const selectedMeasure=measurements.find((item:any)=>item.key===form.measurement_key)
  async function create(event:React.FormEvent){event.preventDefault();setSaving(true);setError('');try{await api('/alarm-rules',token,{method:'POST',body:JSON.stringify({...form,device_id:selected?.id,threshold:Number(form.threshold),deadband:Number(form.deadband),notification_channels:['in_app']})});setOpen(false);setForm({...form,name:''});onChanged()}catch(e:any){setError(e.message)}finally{setSaving(false)}}
  async function toggle(rule:any){await api(`/alarm-rules/${rule.id}/active`,token,{method:'PATCH',body:JSON.stringify({active:!rule.active})});onChanged()}
  async function acknowledge(id:string){await api(`/alarms/${id}/acknowledge`,token,{method:'POST'});onChanged()}
  return <section className="alarm-workspace"><div className="alarm-heading"><div><p className="ops-eyebrow">ISA-18.2 INSPIRED WORKFLOW</p><h2>Allarmi e notifiche</h2><p>Priorità visibile, presa visione operatore e rientro automatico con isteresi.</p></div><button className="ops-primary" onClick={()=>setOpen(!open)}><SlidersHorizontal/>Nuova soglia</button></div>{open&&<form className="threshold-form" onSubmit={create}><div className="form-title"><div><b>Configura una soglia</b><span>La regola viene valutata sull’Edge a ogni acquisizione.</span></div><button type="button" onClick={()=>setOpen(false)}>Chiudi</button></div><label className="wide">Nome regola<input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="es. Sovraccarico contatore generale"/></label><label className="wide">Grandezza<select value={form.measurement_key} onChange={e=>setForm({...form,measurement_key:e.target.value})}>{measurements.map((item:any)=><option key={item.key} value={item.key}>{item.label} ({item.unit||'—'})</option>)}</select></label><label>Condizione<select value={form.condition} onChange={e=>setForm({...form,condition:e.target.value})}><option value="above">Superiore a</option><option value="below">Inferiore a</option></select></label><label>Soglia ({selectedMeasure?.unit||'unità'})<input type="number" step="any" required value={form.threshold} onChange={e=>setForm({...form,threshold:e.target.value})}/></label><label>Isteresi ({selectedMeasure?.unit||'unità'})<input type="number" min="0" step="any" value={form.deadband} onChange={e=>setForm({...form,deadband:e.target.value})}/></label><label>Priorità<select value={form.severity} onChange={e=>setForm({...form,severity:e.target.value})}><option value="warning">Avviso</option><option value="high">Alta</option><option value="critical">Critica</option><option value="info">Informativa</option></select></label><div className="notification-choice wide"><Bell/><span><b>Centro notifiche Edge</b><small>Canale locale attivo e registrato nell’audit log.</small></span><Check/></div>{error&&<p className="form-error wide">{error}</p>}<button className="ops-primary wide" disabled={saving}>{saving?'Salvataggio…':'Attiva soglia'}</button></form>}<div className="alarm-columns"><div className="active-alarms"><div className="subhead"><h3>Eventi attivi</h3><span>{data.active_alarms?.length||0}</span></div>{data.active_alarms?.length?data.active_alarms.map((event:any)=><article key={event.id} className={`alarm-event ${event.severity}`}><div className="alarm-priority"><AlertTriangle/><span>{severityLabel[event.severity]||event.severity}</span></div><div className="alarm-copy"><b>{event.description}</b><small>{time(event.opened_at)} · {event.measurement_key}</small></div>{event.status==='open'?<button onClick={()=>acknowledge(event.id)}>Prendi visione</button>:<span className="ack"><Check/>Presa visione</span>}</article>):<div className="clear-state"><ShieldCheck/><b>Nessun allarme attivo</b><span>L’impianto opera entro le soglie configurate.</span></div>}</div><div className="rules-list"><div className="subhead"><h3>Soglie configurate</h3><span>{rules.length}</span></div>{rules.map(rule=><article key={rule.id} className={!rule.active?'disabled':''}><span className={`severity-dot ${rule.severity}`}/><div><b>{rule.name}</b><small>{rule.measurement_key} · {conditionLabel[rule.kind]} {rule.threshold??`${rule.low}–${rule.high}`} · isteresi {rule.deadband||0}</small></div><button className={`switch ${rule.active?'on':''}`} onClick={()=>toggle(rule)} aria-label={`${rule.active?'Disattiva':'Attiva'} ${rule.name}`}><i/></button></article>)}</div></div></section>
}

function EnergyScope({topology,selection,onSelect}:{topology:any,selection:string,onSelect:(id:string)=>void}){
  const roots=topology?.roots||[]
  const flatten=(nodes:any[]):any[]=>nodes.flatMap(node=>[node,...flatten(node.children||[])])
  const all=flatten(roots),metered=all.filter(node=>node.meter)
  const main=metered.find(node=>node.category==='meter')||metered[0]
  const selectedNode=all.find(node=>node.meter?.id===selection)
  const downstream=metered.filter(node=>node!==main)
  const render=(node:any,depth=0):React.ReactNode=><React.Fragment key={node.id}><button className={`${node.meter?.id===selection?'selected':''} ${!node.meter?'structural':''}`} style={{paddingLeft:12+depth*17}} onClick={()=>node.meter&&onSelect(node.meter.id)} disabled={!node.meter}><span className="tree-connector"/><span className="tree-device-icon">{node.meter?<Gauge/>:<Factory/>}</span><span className="tree-label"><b>{node.name}</b><small>{node.meter?`${node.meter.manufacturer} ${node.meter.model}`:node.category}</small></span>{node.effective_power_kw!==null&&<strong>{fmt(node.effective_power_kw)} <small>kW</small></strong>}<i className={node.meter?.status||''}/></button>{node.children?.map((child:any)=>render(child,depth+1))}</React.Fragment>
  const unassignedSelected=topology?.unassigned_devices?.find((device:any)=>device.id===selection)
  const reference=selection==='plant'?main:selectedNode||{meter:unassignedSelected,measured_power_kw:unassignedSelected?.power_kw,measured_energy_kwh:unassignedSelected?.energy_kwh}
  return <section className="energy-scope"><div className="energy-tree"><header><div><p className="ops-eyebrow">GERARCHIA ENERGETICA</p><h2>Albero impianto</h2></div><span>{metered.length} misuratori</span></header><button className={`plant-root ${selection==='plant'?'selected':''}`} onClick={()=>onSelect('plant')}><span className="tree-device-icon"><Network/></span><span className="tree-label"><b>Vista intero impianto</b><small>Totale autorevole dal generale</small></span><strong>{fmt(topology?.plant?.power_kw)} <small>kW</small></strong></button><div className="energy-tree-scroll">{roots.map((root:any)=>render(root))}{topology?.unassigned_devices?.length>0&&<div className="unassigned"><span>NON ASSOCIATI</span>{topology.unassigned_devices.map((device:any)=><button key={device.id} className={selection===device.id?'selected':''} onClick={()=>onSelect(device.id)}><span className="tree-device-icon"><Gauge/></span><span className="tree-label"><b>{device.name}</b><small>{device.manufacturer} {device.model}</small></span><strong>{fmt(device.power_kw)} <small>kW</small></strong></button>)}</div>}</div></div><div className="scope-summary">{selection==='plant'?<><header><div><p className="ops-eyebrow">BILANCIO ISTANTANEO</p><h2>Vista aggregata dell’impianto</h2></div><span className="calculation-badge">Monte autorevole</span></header><div className="balance-cards"><article><span>Assorbimento generale</span><strong>{fmt(main?.measured_power_kw??topology?.plant?.power_kw)} <small>kW</small></strong><p>{main?.name||'Somma delle radici misurate'}</p></article><article><span>Utenze a valle</span><strong>{fmt(main?.downstream_power_kw)} <small>kW</small></strong><p>Somma dei rami secondari misurati</p></article><article className={(main?.residual_power_kw||0)<0?'danger':'amber'}><span>Non attribuita</span><strong>{fmt(main?.residual_power_kw)} <small>kW</small></strong><p>Generale meno utenze a valle</p></article><article><span>Copertura misura</span><strong>{fmt(main?.coverage_percent)} <small>%</small></strong><p>Quota attribuita ai sotto-contatori</p></article></div><div className="allocation"><div className="allocation-head"><b>Ripartizione utenze</b><span>Il totale non somma mai generale e sotto-contatori</span></div>{downstream.length?downstream.map(node=>{const percentage=main?.measured_power_kw?Math.max(0,node.effective_power_kw/main.measured_power_kw*100):0;return <button key={node.id} onClick={()=>onSelect(node.meter.id)}><span><b>{node.name}</b><small>{node.meter.name}</small></span><div><i style={{width:`${Math.min(percentage,100)}%`}}/></div><strong>{fmt(node.effective_power_kw)} kW<small>{fmt(percentage)}%</small></strong></button>}):<div className="allocation-empty">Associa i multimetri alle utenze secondarie per ottenere la ripartizione.</div>}</div><p className="counter-note">Bilancio ultime 24 ore: generale <b>{fmt(main?.measured_energy_24h_kwh)} kWh</b> · utenze a valle <b>{fmt(main?.downstream_energy_24h_kwh)} kWh</b> · non attribuita <b>{fmt(main?.residual_energy_24h_kwh)} kWh</b>. I valori sono delta sullo stesso intervallo; le letture assolute dei contatori non vengono sommate impropriamente.</p></>:<><header><div><p className="ops-eyebrow">DISPOSITIVO SELEZIONATO</p><h2>{selectedNode?.name||'Dispositivo non associato'}</h2></div><span className="calculation-badge">Dashboard dedicata</span></header><div className="selected-meter-card"><span className="tree-device-icon"><Gauge/></span><div><b>{reference?.meter?.name||'Dispositivo'}</b><small>{reference?.meter?.manufacturer} {reference?.meter?.model}</small></div><LiveBadge status={reference?.meter?.status}/></div><div className="balance-cards compact"><article><span>Potenza</span><strong>{fmt(reference?.measured_power_kw??reference?.meter?.power_kw)} <small>kW</small></strong></article><article><span>Energia</span><strong>{fmt(reference?.measured_energy_kwh??reference?.meter?.energy_kwh)} <small>kWh</small></strong></article><article><span>Carichi a valle</span><strong>{fmt(reference?.downstream_power_kw)} <small>kW</small></strong></article><article><span>Residuo</span><strong>{fmt(reference?.residual_power_kw)} <small>kW</small></strong></article></div><p className="device-depth-note"><ChevronRight/>La dashboard tecnica completa del dispositivo prosegue sotto con andamento, fasi, qualità elettrica, registri live e soglie dedicate.</p></>}</div></section>
}

function ElectricalDetail({measurements}:{measurements:any[]}){
  const map=Object.fromEntries(measurements.map(item=>[item.key,item]))
  const phases=['l1','l2','l3'].map((phase,index)=>({name:`L${index+1}`,voltage:map[`electrical.voltage.${phase}n`],current:map[`electrical.current.${phase}`],power:map[`electrical.active_power.${phase}`],pf:map[`electrical.power_factor.${phase}`],thdv:map[`electrical.thd.voltage.${phase}`],thdi:map[`electrical.thd.current.${phase}`]}))
  const hasPhases=phases.some(phase=>phase.voltage||phase.current||phase.power)
  const quality=[map['electrical.unbalance.voltage'],map['electrical.unbalance.current'],map['electrical.thd.voltage.l1'],map['electrical.thd.current.l1']].filter(Boolean)
  return <section className="ops-section electrical-detail"><header><div><p className="ops-eyebrow">DASHBOARD DISPOSITIVO</p><h2>Analisi elettrica approfondita</h2></div><span>Valori normalizzati</span></header>{hasPhases?<div className="phase-table"><div className="phase-row head"><span>Fase</span><span>Tensione</span><span>Corrente</span><span>Potenza attiva</span><span>Cos φ</span><span>THD V / I</span></div>{phases.map(phase=><div className="phase-row" key={phase.name}><b>{phase.name}</b><strong>{fmt(phase.voltage?.value)} <small>V</small></strong><strong>{fmt(phase.current?.value)} <small>A</small></strong><strong>{fmt(phase.power?.value)} <small>kW</small></strong><strong>{fmt(phase.pf?.value,2)}</strong><strong>{fmt(phase.thdv?.value)} / {fmt(phase.thdi?.value)} <small>%</small></strong></div>)}</div>:<div className="detail-unavailable"><Activity/><span><b>Misure per fase non disponibili su questo profilo</b><small>La vista si popolerà automaticamente con PAC2200/PAC3200/PAC3220 o altri multimetri trifase compatibili.</small></span></div>}{quality.length>0&&<div className="quality-strip">{quality.map(item=><div key={item.key}><span>{item.label}</span><strong>{fmt(item.value)} <small>{item.unit}</small></strong></div>)}</div>}</section>
}

export function EdgeOperations({token,onOpenPlant,focus='dashboard'}:{token:string,onOpenPlant?:()=>void,focus?:'dashboard'|'live'|'alarms'}){
  const [data,setData]=useState<any>({measurements:[],devices:[],series:[],active_alarms:[]}),[topology,setTopology]=useState<any>({roots:[],plant:{},unassigned_devices:[]}),[rules,setRules]=useState<any[]>([]),[selection,setSelection]=useState('plant'),[query,setQuery]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true)
  const load=async(silent=false)=>{if(!silent)setLoading(true);setError('');try{const suffix=selection!=='plant'?`?device_id=${selection}`:'';const [dashboard,alarmRules,tree]=await Promise.all([api(`/dashboard${suffix}`,token),api('/alarm-rules',token),api('/operations/tree',token)]);setData(dashboard);setRules(alarmRules);setTopology(tree)}catch(e:any){setError(e.message)}finally{setLoading(false)}}
  useEffect(()=>{void load();const timer=setInterval(()=>void load(true),5000);return()=>clearInterval(timer)},[token,selection])
  if(loading&&!data.primary_meter)return <div className="ops-loading"><Gauge/><span>Preparazione console operativa…</span></div>
  const meter=data.primary_meter
  const selectedLive=focus==='live'&&selection!=='plant'
  return <div className="operations">
    <header className="ops-header"><div><p className="ops-eyebrow">EDGE OPERATIONS · {focus==='dashboard'?'OVERVIEW':focus==='live'?'LIVE DEVICE STUDIO':'ALARM MANAGEMENT'}</p><h1>{focus==='dashboard'?(data.site_name||'Impianto Edge'):focus==='live'?'Dispositivi e dati live':'Centro allarmi'}</h1><p>{selection==='plant'?'Vista aggregata · seleziona un dispositivo dall’albero per aprire il cockpit dedicato':meter?`${meter.name} · ${meter.manufacturer} ${meter.model}`:'Seleziona un dispositivo'}</p></div><div className="ops-actions"><LiveBadge status={meter?.status}/><button onClick={()=>load()} title="Aggiorna"><RefreshCw/></button>{onOpenPlant&&<button className="manage" onClick={onOpenPlant}><Factory/>Gestisci impianto</button>}</div></header>
    {error&&<div className="ops-error">{error}</div>}
    <div className="ops-toolbar"><label><span>Ambito di monitoraggio</span><select value={selection} onChange={e=>setSelection(e.target.value)}><option value="plant">Intero impianto · vista aggregata</option>{data.devices?.map((device:any)=><option value={device.id} key={device.id}>{device.name} · {device.manufacturer} {device.model}</option>)}</select></label><div><Clock3/><span>Ultimo dato valido<small>{time(data.updated_at)}</small></span></div><div><Activity/><span>Ciclo di acquisizione<small>{fmt(meter?.cycle_duration_ms,0)} ms</small></span></div><div><Bell/><span>Soglie attive<small>{data.active_rules||0}</small></span></div></div>
    {focus!=='alarms'&&<EnergyScope topology={topology} selection={selection} onSelect={setSelection}/>}
    {focus!=='alarms'&&(selectedLive?<DeviceLiveCockpit token={token} data={data} query={query} setQuery={setQuery}/>:<><div className="ops-kpis"><SummaryCard label={selection==='plant'?'Potenza generale':'Potenza attiva'} value={data.power_kw} unit="kW" icon={Zap} detail={`Picco recente ${fmt(data.peak_kw)} kW`}/><SummaryCard label={selection==='plant'?'Energia generale':'Energia'} value={data.energy_kwh} unit="kWh" icon={Gauge} tone="blue" detail="Valore normalizzato"/><SummaryCard label="Fattore di potenza" value={data.power_factor} unit="" icon={Activity} tone="amber" detail="Totale trifase"/><SummaryCard label="Frequenza" value={data.frequency_hz} unit="Hz" icon={Wifi} tone="purple" detail={`${data.devices_online||0}/${data.devices_total||0} strumenti online`}/></div>{focus==='dashboard'&&<div className="ops-main-grid"><section className="ops-section power-panel"><header><div><p className="ops-eyebrow">POTENZA ATTIVA</p><h2>Profilo in tempo reale</h2></div><span>Ultimi {data.series?.length||0} campioni</span></header><Trend series={data.series||[]}/></section><section className="ops-section health-panel"><header><div><p className="ops-eyebrow">AFFIDABILITÀ</p><h2>Stato Edge</h2></div></header><div className="health-list"><div><Wifi/><span><b>Comunicazione strumento</b><small>Ultimo polling {time(meter?.last_valid_poll_at)}</small></span><LiveBadge status={meter?.status}/></div><div><ShieldCheck/><span><b>Qualità del dato</b><small>Validazione e normalizzazione</small></span><em className="good">{data.quality}</em></div><div><Bell/><span><b>Allarmi da gestire</b><small>Inclusi quelli presi in visione</small></span><strong>{data.open_alarms||0}</strong></div><div><Settings2/><span><b>Sincronizzazione</b><small>Eventi in coda verso Control Room</small></span><strong>{data.sync_pending||0}</strong></div></div></section></div>}<ElectricalDetail measurements={data.measurements||[]}/><MeasurementGrid measurements={data.measurements||[]} query={query} setQuery={setQuery}/></>)}
    {focus!=='live'&&<AlarmCenter token={token} data={data} rules={rules} onChanged={()=>load(true)}/>}<footer className="ops-footer"><span><ShieldCheck/>Acquisizione locale autonoma</span><span><ChevronRight/>Valori vendor-neutral per dashboard, KPI e allarmi</span></footer>
  </div>
}
