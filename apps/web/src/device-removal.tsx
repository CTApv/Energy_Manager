import { AlertTriangle, Archive, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'

const apiBase = import.meta.env.VITE_API_URL || '/api'

async function api(path:string, token:string, options:RequestInit={}) {
  const response=await fetch(`${apiBase}${path}`,{...options,headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`}})
  if(!response.ok) throw new Error((await response.json().catch(()=>({}))).detail||'Operazione non riuscita')
  return response.json()
}

export function DeviceRemoval({device,token,onClose,onRemoved}:{device:any,token:string,onClose:()=>void,onRemoved:()=>Promise<void>}){
  const [impact,setImpact]=useState<any>(null),[confirm,setConfirm]=useState(''),[removeBindings,setRemoveBindings]=useState(false),[purge,setPurge]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{api(`/devices/${device.id}/removal-impact`,token).then(setImpact).catch(e=>setError(e.message))},[device.id,token])
  async function remove(){setBusy(true);setError('');try{await api(`/devices/${device.id}`,token,{method:'DELETE',body:JSON.stringify({confirm_name:confirm,remove_bindings:removeBindings,purge_history:purge})});await onRemoved();onClose()}catch(e:any){setError(e.message)}finally{setBusy(false)}}
  return <div className="confirm-backdrop" role="dialog" aria-modal="true" aria-label="Rimuovi dispositivo"><section className="confirm-dialog"><header><span className="danger-symbol"><Trash2/></span><div><p>DISMISSIONE CONTROLLATA</p><h2>Rimuovere “{device.name}”?</h2></div><button onClick={onClose} aria-label="Chiudi"><X/></button></header>{error&&<div className="alert">{error}</div>}<div className="impact-grid"><article><b>{impact?.bindings??'—'}</b><span>associazioni nell’albero</span></article><article><b>{impact?.samples??'—'}</b><span>campioni storici</span></article><article><b>{impact?.alarm_rules??'—'}</b><span>regole disattivate</span></article><article><b>{impact?.alarm_events??'—'}</b><span>eventi conservati</span></article></div><div className="preserve-note"><Archive/><span><b>Lo storico viene conservato</b><small>Il dispositivo non sarà più interrogato né mostrato nella configurazione attiva; regole e acquisizione vengono fermate, ma dati ed eventi passati restano disponibili.</small></span></div>{impact?.bindings>0&&<label className="check-choice"><input type="checkbox" checked={removeBindings} onChange={e=>setRemoveBindings(e.target.checked)}/><span><b>Rimuovi anche le associazioni dall’albero</b><small>Necessario per completare la dismissione.</small></span></label>}<label className="check-choice dangerous"><input type="checkbox" checked={purge} onChange={e=>setPurge(e.target.checked)}/><span><b>Elimina definitivamente anche lo storico</b><small>Operazione irreversibile. Normalmente va lasciata disattivata.</small></span></label><label className="confirm-name">Scrivi <b>{device.name}</b> per confermare<input value={confirm} onChange={e=>setConfirm(e.target.value)} autoFocus/></label><footer><button className="icon-button" onClick={onClose}>Annulla</button><button className="danger-button" disabled={busy||confirm.trim()!==device.name.trim()||(impact?.bindings>0&&!removeBindings)} onClick={remove}><AlertTriangle/>{busy?'Rimozione…':'Rimuovi dispositivo'}</button></footer></section></div>
}
