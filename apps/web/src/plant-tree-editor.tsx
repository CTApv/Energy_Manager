import React, { useEffect, useMemo, useState } from 'react'
import { Factory, GripVertical, Pencil, Plus, Save, Trash2, X } from 'lucide-react'

const apiBase = import.meta.env.VITE_API_URL || '/api'
const blank = { name: '', parent_id: '', category: 'asset', description: '', active: true }

type Props = {
  token: string
  assets: any[]
  bindings: any[]
  onChanged: () => Promise<void>
  notify: (message: string) => void
  fail: (error: any) => void
}

async function api(path: string, token: string, options: RequestInit) {
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Operazione non riuscita')
  return response.json()
}

export function PlantTreeEditor({ token, assets, bindings, onChanged, notify, fail }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<any>(blank)
  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const ordered = useMemo(() => [...assets].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name)), [assets])
  const selected = assets.find(item => item.id === editingId)
  useEffect(() => {
    if (editingId && !selected) { setEditingId(null); setForm(blank) }
  }, [editingId, selected])

  function edit(item?: any) {
    setEditingId(item?.id || null)
    setForm(item ? { name: item.name, parent_id: item.parent_id || '', category: item.category, description: item.description || '', active: item.active } : blank)
  }

  async function save(event: React.FormEvent) {
    event.preventDefault()
    const siblings = assets.filter(item => (item.parent_id || '') === form.parent_id && item.id !== editingId)
    const payload = { ...form, parent_id: form.parent_id || null, sort_order: editingId ? selected?.sort_order || 0 : siblings.length }
    try {
      await api(editingId ? `/assets/${editingId}` : '/assets', token, { method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload) })
      notify(editingId ? 'Nodo aggiornato' : 'Nodo aggiunto')
      edit(); await onChanged()
    } catch (error) { fail(error) }
  }

  function isDescendant(candidateId: string, ancestorId: string) {
    let current = assets.find(item => item.id === candidateId)
    while (current?.parent_id) {
      if (current.parent_id === ancestorId) return true
      current = assets.find(item => item.id === current.parent_id)
    }
    return false
  }

  async function move(parentId: string | null) {
    const item = assets.find(value => value.id === draggedId)
    setDropTarget(null); setDraggedId(null)
    if (!item || item.id === parentId || (parentId && isDescendant(parentId, item.id))) return
    const siblings = assets.filter(value => value.parent_id === parentId && value.id !== item.id)
    try {
      await api(`/assets/${item.id}`, token, { method: 'PUT', body: JSON.stringify({ name: item.name, parent_id: parentId, category: item.category, description: item.description || '', active: item.active, sort_order: siblings.length }) })
      notify(parentId ? `“${item.name}” spostato nel nuovo ramo` : `“${item.name}” spostato alla radice`)
      await onChanged()
    } catch (error) { fail(error) }
  }

  async function reorder(item: any, direction: -1 | 1) {
    const siblings = ordered.filter(value => value.parent_id === item.parent_id)
    const index = siblings.findIndex(value => value.id === item.id)
    const other = siblings[index + direction]
    if (!other) return
    try {
      await Promise.all([
        api(`/assets/${item.id}`, token, { method: 'PUT', body: JSON.stringify({ ...item, sort_order: other.sort_order }) }),
        api(`/assets/${other.id}`, token, { method: 'PUT', body: JSON.stringify({ ...other, sort_order: item.sort_order }) }),
      ])
      await onChanged()
    } catch (error) { fail(error) }
  }

  async function remove(item:any) {
    if (!window.confirm(`Rimuovere il nodo “${item.name}”? Prima devono essere rimossi figli e misure associate.`)) return
    try {
      await api(`/assets/${item.id}`, token, { method: 'DELETE' })
      notify('Nodo rimosso'); edit(); await onChanged()
    } catch (error) { fail(error) }
  }

  const branch = (node: any, depth = 0): React.ReactNode => (
    <React.Fragment key={node.id}>
      <div
        className={`tree-edit-row ${dropTarget === node.id ? 'drop-target' : ''}`}
        style={{ paddingLeft: 12 + depth * 25 }}
        draggable
        onDragStart={event => { setDraggedId(node.id); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', node.id) }}
        onDragEnd={() => { setDraggedId(null); setDropTarget(null) }}
        onDragOver={event => { event.preventDefault(); event.stopPropagation(); if (draggedId !== node.id) setDropTarget(node.id) }}
        onDrop={event => { event.preventDefault(); event.stopPropagation(); void move(node.id) }}
      >
        <GripVertical className="drag-handle" aria-label="Trascina nodo" />
        <span className="asset-icon"><Factory size={15} /></span>
        <span className="tree-edit-label"><b>{node.name}</b><small>{node.category} · {bindings.filter(binding => binding.asset_id === node.id).length} misure</small></span>
        <span className="tree-order"><button onClick={() => void reorder(node, -1)} title="Sposta prima">↑</button><button onClick={() => void reorder(node, 1)} title="Sposta dopo">↓</button></span>
        <button className="row-action" onClick={() => edit(node)} title="Modifica nodo"><Pencil size={14} /></button>
        <button className="row-action danger" onClick={() => void remove(node)} title="Rimuovi nodo"><Trash2 size={14} /></button>
      </div>
      {ordered.filter(item => item.parent_id === node.id).map(item => branch(item, depth + 1))}
    </React.Fragment>
  )

  return <div className="plant-grid tree-editor-grid">
    <section className="panel">
      <header><h2>Gerarchia energetica</h2><button className="icon-button compact" onClick={() => edit()}><Plus size={14} />Nuovo nodo</button></header>
      <div className="tree-editor-help">Trascina un nodo sopra un altro per renderlo figlio. Usa le frecce per ordinare i nodi dello stesso livello.</div>
      <div className={`root-drop ${dropTarget === '__root__' ? 'drop-target' : ''}`} onDragOver={event => { event.preventDefault(); setDropTarget('__root__') }} onDrop={event => { event.preventDefault(); void move(null) }}>Rilascia qui per portare il nodo alla radice dell’impianto</div>
      <div className="tree editable-tree">{ordered.filter(item => !item.parent_id).map(item => branch(item))}</div>
    </section>
    <section className="panel">
      <header><h2>{editingId ? 'Modifica nodo' : 'Nuovo nodo'}</h2>{editingId && <button className="row-action" onClick={() => edit()} title="Annulla"><X size={15} /></button>}</header>
      <form className="form-grid" onSubmit={save}>
        <label className="wide">Nome<input value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} required /></label>
        <label className="wide">Nodo superiore<select value={form.parent_id} onChange={event => setForm({ ...form, parent_id: event.target.value })}><option value="">Radice impianto</option>{ordered.filter(item => item.id !== editingId && !isDescendant(item.id, editingId || '')).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label className="wide">Categoria<select value={form.category} onChange={event => setForm({ ...form, category: event.target.value })}><option value="asset">Asset</option><option value="branch">Ramo</option><option value="line">Linea</option><option value="meter">Contatore</option><option value="grid">Punto di consegna rete</option><option value="solar">Campo fotovoltaico</option><option value="storage">Sistema di accumulo</option><option value="ev">Ricarica veicoli</option><option value="machine">Macchina</option><option value="service">Servizio</option></select></label>
        <label className="wide">Descrizione<textarea value={form.description} onChange={event => setForm({ ...form, description: event.target.value })} placeholder="Funzione, quadro o area servita" /></label>
        <button className="primary-button wide"><Save size={15} />{editingId ? 'Salva modifiche' : 'Aggiungi nodo'}</button>
      </form>
    </section>
  </div>
}
