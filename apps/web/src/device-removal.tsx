import { Archive, DatabaseZap, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'

const apiBase = import.meta.env.VITE_API_URL || '/api'

async function api(path:string, token:string, options:RequestInit={}) {
  const response=await fetch(`${apiBase}${path}`,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`}})
  if(!response.ok) throw new Error((await response.json().catch(()=>({}))).detail||'Operazione non riuscita')
  return response.json()
}

export function DeviceRemoval({device,token,onClose,onRemoved}:{device:any,token:string,onClose:()=>void,onRemoved:()=>Promise<void>}){
  const [impact,setImpact]=useState<any>(null),[choice,setChoice]=useState<'keep'|'purge'>('keep'),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{api(`/devices/${device.id}/removal-impact`,token).then(setImpact).catch(e=>setError(e.message))},[device.id,token])
  async function remove(){setBusy(true);setError('');try{await api(`/devices/${device.id}`,token,{method:'DELETE',body:JSON.stringify({purge_history:choice==='purge'})});await onRemoved();onClose()}catch(e:any){setError(e.message)}finally{setBusy(false)}}
  return <div className="confirm-backdrop" role="dialog" aria-modal="true" aria-label="Elimina dispositivo"><section className="confirm-dialog simple-removal"><header><span className="danger-symbol"><Trash2/></span><div><p>RIMOZIONE DISPOSITIVO</p><h2>Sei sicuro di voler eliminare “{device.name}”?</h2></div><button onClick={onClose} aria-label="Chiudi"><X/></button></header>{error&&<div className="alert">{error}</div>}<p className="removal-explain">Il dispositivo sparirà dalla vista live e non verrà più interrogato. Le associazioni nell’albero saranno rimosse automaticamente e le regole collegate verranno disattivate.</p><div className="impact-grid"><article><b>{impact?.bindings??'—'}</b><span>collegamenti rimossi</span></article><article><b>{impact?.samples??'—'}</b><span>dati storici</span></article><article><b>{impact?.alarm_rules??'—'}</b><span>regole disattivate</span></article><article><b>{impact?.alarm_events??'—'}</b><span>eventi registrati</span></article></div><fieldset className="history-choice"><legend>Cosa vuoi fare con i dati già raccolti?</legend><button type="button" className={choice==='keep'?'selected':''} onClick={()=>setChoice('keep')}><span><Archive/></span><div><b>Conserva lo storico</b><small>Scelta consigliata. Grafici, consumi ed eventi passati restano in memoria.</small></div><i/></button><button type="button" className={`purge ${choice==='purge'?'selected':''}`} onClick={()=>setChoice('purge')}><span><DatabaseZap/></span><div><b>Elimina anche lo storico</b><small>Cancella definitivamente tutti i campioni raccolti da questo dispositivo.</small></div><i/></button></fieldset><footer><button className="icon-button" onClick={onClose}>Annulla</button><button className="danger-button" disabled={busy} onClick={remove}><Trash2/>{busy?'Eliminazione…':'Elimina dispositivo'}</button></footer></section></div>
}
