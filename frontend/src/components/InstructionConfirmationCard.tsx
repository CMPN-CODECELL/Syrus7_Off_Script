'use client'

import { useEffect, useState } from 'react'
import { CheckCircle2, Clock, XCircle } from 'lucide-react'

interface InstructionDraft {
  name: string
  symbol: string
  condition_type: 'PRICE_ABOVE' | 'PRICE_BELOW'
  condition_value: number
  action_side: 'BUY' | 'SELL'
  action_quantity: number
  action_order_type?: string
  expires_in_hours?: number
}

interface Props {
  draft: InstructionDraft
}

export default function InstructionConfirmationCard({ draft }: Props) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)
  const [timeLeft, setTimeLeft] = useState(60)

  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(previous => {
        if (previous <= 1) {
          clearInterval(timer)
          setResult({ success: false, message: 'Approval window expired. Please create the instruction again.' })
          return 0
        }
        return previous - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const condition = draft.condition_type === 'PRICE_ABOVE'
    ? 'rises above'
    : draft.condition_type === 'PRICE_BELOW'
      ? 'falls below'
      : 'changes by'

  const approve = async () => {
    setLoading(true)
    try {
      const response = await fetch('http://localhost:8000/instructions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...draft, raw_instruction: draft.name }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(data.detail || data.message || `Activation failed (${response.status})`)
      }
      setResult({ success: true, message: 'Standing instruction activated.' })
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to activate this instruction.'
      setResult({ success: false, message })
    } finally {
      setLoading(false)
    }
  }

  const reject = () => setResult({ success: false, message: 'Instruction was not activated.' })

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
          <h3 className="text-base font-bold accent-text">{draft.name}</h3>
          <p className="text-xs muted-text mt-1">STANDING INSTRUCTION</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: timeLeft < 10 ? 'var(--danger)' : 'var(--warning)' }}>
          <Clock size={12} />{timeLeft}s
        </div>
      </div>

      <div className="space-y-2 text-sm">
        <p><span className="muted-text">When: </span><span className="font-mono">{draft.symbol} {condition} ₹{draft.condition_value.toLocaleString('en-IN')}</span></p>
        <p><span className="muted-text">Then: </span><span className="font-mono">{draft.action_side} {draft.action_quantity} shares ({draft.action_order_type || 'MARKET'})</span></p>
        {draft.expires_in_hours && (
          <p><span className="muted-text">Duration: </span>{draft.expires_in_hours >= 24 ? `${Math.round(draft.expires_in_hours / 24)} days` : `${draft.expires_in_hours} hours`}</p>
        )}
      </div>

      <p className="text-xs muted-text">
        Once activated, this rule may submit the listed order automatically when its condition is met.
      </p>

      <div className="flex gap-3">
        <button
          onClick={approve}
          disabled={loading || timeLeft === 0}
          className="flex-1 py-2.5 rounded-lg font-semibold text-sm transition-all disabled:opacity-30 accent-glow"
          style={{ background: 'var(--accent)', color: '#000' }}
        >
          {loading ? 'Activating...' : 'Approve & Activate Instruction'}
        </button>
        <button
          onClick={reject}
          disabled={loading}
          className="px-5 py-2.5 rounded-lg font-semibold text-sm transition-all"
          style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
        >
          Reject
        </button>
      </div>
    </div>
  )
}
