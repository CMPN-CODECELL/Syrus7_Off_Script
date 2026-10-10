'use client'
import { useState, useEffect } from 'react'
import { Plus, Trash2, Clock, CheckCircle2, AlertCircle } from 'lucide-react'

export default function InstructionsPanel({ onCreate, stopLossOnly = false }: { onCreate?: () => void; stopLossOnly?: boolean }) {
  const [instructions, setInstructions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)

  const fetchInstructions = async () => {
    try {
      const res = await fetch('http://localhost:8000/instructions/')
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
      setInstructions(data.instructions)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load instructions.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInstructions()
    const timer = setInterval(fetchInstructions, 5000) // Refresh every 5s
    return () => clearInterval(timer)
  }, [])

  const updateInstruction = async (id: string, action: 'cancel' | 'resume') => {
    setBusyId(id)
    setError('')
    try {
      const res = action === 'cancel'
        ? await fetch(`http://localhost:8000/instructions/${id}`, { method: 'DELETE' })
        : await fetch(`http://localhost:8000/instructions/${id}/resume`, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
      await fetchInstructions()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to update this instruction.')
    } finally {
      setBusyId(null)
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'ACTIVE':   return <Clock size={14} style={{ color: 'var(--accent)' }} />
      case 'TRIGGERED': return <CheckCircle2 size={14} style={{ color: 'var(--success)' }} />
      case 'CANCELLED': return <AlertCircle size={14} style={{ color: 'var(--danger)' }} />
      case 'EXPIRED':   return <AlertCircle size={14} style={{ color: 'var(--text-muted)' }} />
      default:         return <AlertCircle size={14} style={{ color: 'var(--text-muted)' }} />
    }
  }

  const visibleInstructions = stopLossOnly
    ? instructions.filter(inst => inst.condition_type === 'PRICE_BELOW' && inst.action_side === 'SELL')
    : instructions

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm muted-text">Loading standing instructions...</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">{stopLossOnly ? 'Stop-loss management' : 'Standing instructions'}</h2>
          <button onClick={onCreate} className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all"
                  style={{ background: 'var(--accent)', color: '#000' }}>
            <Plus size={12} />
            {stopLossOnly ? 'Create stop-loss' : 'Create via Copilot'}
          </button>
        </div>
        <p className="text-xs muted-text mt-1">
          {stopLossOnly ? 'Manage price-below sell rules for your demo holdings. Activating a rule pre-authorizes its simulated order if the trigger is reached.' : 'Review, pause, resume, or cancel standing rules. Create new rules through the Copilot.'}
        </p>
      </div>

      {/* Instructions List */}
      <div className="flex-1 overflow-y-auto p-4">
        {error && <p role="alert" className="mb-3 rounded border p-3 text-sm" style={{ borderColor: 'var(--danger)', color: 'var(--danger)' }}>{error}</p>}
        {visibleInstructions.length === 0 ? (
          <div className="text-center py-12">
            <Clock size={32} className="mx-auto mb-3 muted-text" />
            <h3 className="font-medium mb-2">{stopLossOnly ? 'No stop-loss rules yet' : 'No standing instructions'}</h3>
            <p className="text-sm muted-text mb-4">
              Create automated trading rules by saying things like:<br />
              "If INFY drops below ₹1750, sell 50 shares"
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {visibleInstructions.map((inst: any) => (
              <div key={inst.id} className="syrus-surface p-4">
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    {getStatusIcon(inst.status)}
                    <h4 className="font-medium">{inst.name}</h4>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`badge badge-${inst.status.toLowerCase()}`}>
                      {inst.status}
                    </span>
                    {inst.status === 'PAUSED' && !inst.triggered_at && (
                      <button
                        onClick={() => updateInstruction(inst.id, 'resume')}
                        disabled={busyId === inst.id}
                        className="rounded px-2 py-1 text-xs transition-colors disabled:opacity-50"
                        style={{ border: '1px solid var(--border)', color: 'var(--accent)' }}
                      >
                        {busyId === inst.id ? 'Working...' : 'Resume'}
                      </button>
                    )}
                    {(inst.status === 'ACTIVE' || inst.status === 'PAUSED') && (
                      <button
                        onClick={() => updateInstruction(inst.id, 'cancel')}
                        disabled={busyId === inst.id}
                        className="p-1 hover:bg-red-500/10 rounded transition-colors"
                        aria-label={`Cancel ${inst.name}`}
                      >
                        <Trash2 size={12} style={{ color: 'var(--danger)' }} />
                      </button>
                    )}
                  </div>
                </div>

                {/* Condition & Action */}
                <div className="text-sm space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs muted-text w-16">WHEN:</span>
                    <span className="font-mono">
                      {inst.symbol} {inst.condition_type.replace('PRICE_', '').toLowerCase()} ₹{inst.condition_value}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs muted-text w-16">THEN:</span>
                    <span className="font-mono">
                      {inst.action_side} {inst.action_quantity} shares ({inst.action_order_type})
                    </span>
                  </div>
                  {inst.triggered_at && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs muted-text w-16">FIRED:</span>
                      <span className="font-mono text-xs">
                        {new Date(inst.triggered_at).toLocaleString()}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
