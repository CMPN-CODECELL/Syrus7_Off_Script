'use client'

import { useEffect, useState } from 'react'
import { CheckCircle2, Clock, XCircle } from 'lucide-react'

interface RiskLimitDraft {
  draft_id: string
  limit_type: string
  label: string
  current_value: number
  value: number
  expires_at: string
}

interface Props {
  draft: RiskLimitDraft
}

const integerLimits = new Set(['MAX_POSITION_SIZE', 'MAX_ORDERS_PER_DAY'])

function formatValue(draft: RiskLimitDraft, value: number) {
  if (integerLimits.has(draft.limit_type)) return value.toLocaleString('en-IN')
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

export default function RiskLimitConfirmationCard({ draft }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)
  const [timeLeft, setTimeLeft] = useState(() => Math.max(0, Math.ceil((Date.parse(draft.expires_at) - Date.now()) / 1000)))

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(Math.max(0, Math.ceil((Date.parse(draft.expires_at) - Date.now()) / 1000)))
    }, 1000)
    return () => clearInterval(timer)
  }, [draft.expires_at])

  const inspectStatus = async () => {
    const response = await fetch(`http://localhost:8000/risk-limits/drafts/${draft.draft_id}`)
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.detail || 'Could not verify the proposal status.')
    if (data.status === 'APPROVED') {
      setResult({ success: true, message: `${draft.label} updated to ${formatValue(draft, draft.value)}.` })
    } else if (data.status === 'REJECTED' || data.status === 'EXPIRED' || data.status === 'STALE') {
      setResult({ success: false, message: `Proposal ${data.status.toLowerCase()}; the risk limit was not changed.` })
    } else {
      setError('The proposal is still pending. You can safely approve it again or reject it.')
    }
  }

  const approve = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`http://localhost:8000/risk-limits/drafts/${draft.draft_id}/approve`, { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || `Approval failed (${response.status})`)
      setResult({ success: true, message: data.message || `${draft.label} updated to ${formatValue(draft, draft.value)}.` })
    } catch (failure) {
      try {
        await inspectStatus()
      } catch {
        setError(failure instanceof Error
          ? `Approval response was unclear (${failure.message}). Check proposal status before retrying.`
          : 'Approval response was unclear. Check proposal status before retrying.')
      }
    } finally {
      setLoading(false)
    }
  }

  const reject = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(`http://localhost:8000/risk-limits/drafts/${draft.draft_id}/reject`, { method: 'POST' })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || `Rejection failed (${response.status})`)
      setResult({ success: false, message: data.message || 'Proposal rejected; no limit was changed.' })
    } catch (failure) {
      try {
        await inspectStatus()
      } catch {
        setError(failure instanceof Error ? failure.message : 'Could not verify the proposal status.')
      }
    } finally {
      setLoading(false)
    }
  }

  if (result) {
    return (
      <div className="confirm-card p-4 flex items-start gap-3" style={{ borderColor: result.success ? 'var(--success)' : 'var(--danger)' }}>
        {result.success
          ? <CheckCircle2 size={20} style={{ color: 'var(--success)' }} />
          : <XCircle size={20} style={{ color: 'var(--danger)' }} />}
        <p className="text-sm" style={{ color: result.success ? 'var(--success)' : 'var(--danger)' }}>{result.message}</p>
      </div>
    )
  }

  return (
    <div className="confirm-card p-5 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-bold accent-text">Change {draft.label}</h3>
          <p className="text-xs muted-text mt-1">RISK BUDGET UPDATE</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: timeLeft < 10 ? 'var(--danger)' : 'var(--warning)' }}>
          <Clock size={12} />{timeLeft}s
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="muted-text text-xs">Current limit</span>
          <p className="font-mono font-bold mt-0.5">{formatValue(draft, draft.current_value)}</p>
        </div>
        <div>
          <span className="muted-text text-xs">Proposed limit</span>
          <p className="font-mono font-bold mt-0.5">{formatValue(draft, draft.value)}</p>
        </div>
      </div>

      <p className="text-xs muted-text">This change applies to future order risk checks. It is saved only if you approve this proposal.</p>
      {error && <p className="text-xs" style={{ color: 'var(--warning)' }}>{error}</p>}

      <div className="flex gap-3">
        <button onClick={approve} disabled={loading || timeLeft === 0} className="flex-1 py-2.5 rounded-lg font-semibold text-sm disabled:opacity-30 accent-glow" style={{ background: 'var(--accent)', color: '#000' }}>
          {loading ? 'Checking...' : timeLeft === 0 ? 'Proposal expired' : 'Approve risk limit'}
        </button>
        <button onClick={reject} disabled={loading} className="px-5 py-2.5 rounded-lg font-semibold text-sm disabled:opacity-50" style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
          Reject
        </button>
      </div>
    </div>
  )
}
