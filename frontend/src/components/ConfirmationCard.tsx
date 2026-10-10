'use client'

import { useEffect, useState } from 'react'
import { CheckCircle2, XCircle, Clock, TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'

interface ConfirmationCardProps {
  draft: {
    order_id: string
    symbol: string
    side: 'BUY' | 'SELL'
    order_type: string
    quantity: number
    price?: number
    trigger_price?: number
    quoted_price?: number
    risk_score?: number
    risk_check_passed?: boolean
    risk_reason?: string
  }
  onApproved: (message: string) => void
  onRejected: (message: string) => void
}

export default function ConfirmationCard({ draft, onApproved, onRejected }: ConfirmationCardProps) {
  const [loading, setLoading] = useState(false)
  const [reconciling, setReconciling] = useState(false)
  const [result, setResult] = useState<{ success: boolean; message: string; status?: string } | null>(null)
  const [timeLeft, setTimeLeft] = useState(60)

  // Countdown timer, cleaned up when the card unmounts.
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timer)
          setResult({ success: false, message: 'Order draft expired. Please request a new quote.' })
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const handleApprove = async () => {
    setLoading(true)
    try {
      const res = await fetch('http://localhost:8000/orders/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: draft.order_id }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || data.message || `Approval failed (${res.status})`)
      }
      if (typeof data.success !== 'boolean') {
        throw new Error(data.detail || data.message || 'The server returned an unexpected approval response.')
      }
      setResult({
        success: data.success,
        status: data.status,
        message: data.success
          ? `Demo broker simulation: ${data.status} — ${data.filled_quantity} shares filled at ₹${data.average_price}. No real trade was placed.`
          : `Demo broker simulation · ${data.status || 'Order failed'}: ${data.message || 'The mock broker did not fill this order.'}`,
      })
      if (data.success) {
        onApproved(`Demo broker simulation: ${data.status} — ${data.filled_quantity} shares filled at ₹${data.average_price}. No real trade was placed.`)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to approve this order.'
      // A lost response does not prove that the backend or broker rejected the
      // request. Keep the card in an unknown/submitted state and offer broker
      // reconciliation so users cannot accidentally submit it a second time.
      setResult({
        success: false,
        status: 'SUBMITTED',
        message: `The demo broker submission status is unknown (${message}). Do not retry this order; check its status first. No real trade was placed by this local demo.`,
      })
    } finally {
      setLoading(false)
    }
  }

  const handleReconcile = async () => {
    setReconciling(true)
    try {
      const res = await fetch(`http://localhost:8000/orders/${draft.order_id}/reconcile`, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `Reconciliation failed (${res.status})`)
      setResult({ success: Boolean(data.success), status: data.status, message: `Demo broker simulation: ${data.message || `Broker status: ${data.status}`} No real trade was placed.` })
      if (data.success) onApproved(`Demo broker simulation: ${data.message || `Order ${data.status} — ${data.filled_quantity} shares filled at ₹${data.average_price}.`} No real trade was placed.`)
    } catch (error) {
      setResult({
        success: false,
        status: 'SUBMITTED',
        message: error instanceof Error ? error.message : 'Could not check the broker order book. Do not submit this order again.',
      })
    } finally {
      setReconciling(false)
    }
  }

  const handleReject = async () => {
    setLoading(true)
    try {
      const res = await fetch('http://localhost:8000/orders/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: draft.order_id, reason: 'Trader rejected' }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `Rejection failed (${res.status})`)
      const message = 'Order draft rejected; no order was sent.'
      setResult({ success: false, message })
      onRejected(message)
    } catch {
      setResult({ success: false, message: 'Failed to reject. Try again.' })
    } finally {
      setLoading(false)
    }
  }

  const quotedPrice = draft.quoted_price ?? draft.price
  const quoteValue = typeof quotedPrice === 'number' && Number.isFinite(quotedPrice) && quotedPrice > 0
    ? quotedPrice
    : null
  const hasValidQuote = quoteValue !== null
  const orderValue = quoteValue === null ? null : draft.quantity * quoteValue
  const riskScore = draft.risk_score ?? 80
  const riskPassed = draft.risk_check_passed !== false
  const riskColor = riskScore >= 80 ? 'var(--success)' : riskScore >= 50 ? 'var(--warning)' : 'var(--danger)'

  if (result) {
    return (
      <div
        className="confirm-card p-4 flex items-start gap-3"
        style={{
          borderColor: result.success ? 'var(--success)' : 'var(--danger)',
          boxShadow: result.success ? '0 0 20px #00ff8833' : '0 0 20px #ff4d6d33',
        }}
      >
        {result.success ? <CheckCircle2 size={20} style={{ color: 'var(--success)' }} /> : <XCircle size={20} style={{ color: 'var(--danger)' }} />}
        <div className="flex-1">
          <p className="text-sm" style={{ color: result.success ? 'var(--success)' : 'var(--danger)' }}>
            {result.message}
          </p>
          {result.status === 'SUBMITTED' && (
            <button
              onClick={handleReconcile}
              disabled={reconciling}
              className="mt-3 rounded px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
              style={{ border: '1px solid var(--warning)', color: 'var(--warning)' }}
            >
              {reconciling ? 'Checking broker…' : 'Check broker status'}
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="confirm-card p-5 space-y-4">

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-bold accent-text tracking-wide">{draft.side} {draft.symbol}</h3>
          <p className="text-xs muted-text mt-0.5">{draft.order_type} ORDER · MOCK BROKER</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs"
             style={{ color: timeLeft < 10 ? 'var(--danger)' : 'var(--warning)' }}>
          <Clock size={12} />
          {timeLeft}s
        </div>
      </div>

      {/* Details grid */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="muted-text text-xs">Quantity</span>
          <p className="font-mono font-bold mt-0.5">{draft.quantity} shares</p>
        </div>
        <div>
          <span className="muted-text text-xs">Price</span>
          <p className="font-mono font-bold mt-0.5">
            {draft.order_type === 'MARKET' ? 'MARKET' : ['SL', 'SL-M'].includes(draft.order_type) ? `Trigger ₹${draft.trigger_price?.toFixed(2) ?? '—'}` : `₹${draft.price?.toFixed(2) ?? '—'}`}
          </p>
        </div>
        <div>
          <span className="muted-text text-xs">Quoted at</span>
          <p className="font-mono font-bold mt-0.5">{quoteValue !== null ? `₹${quoteValue.toFixed(2)}` : 'Unavailable'}</p>
        </div>
        <div>
          <span className="muted-text text-xs">Est. Value</span>
          <p className="font-mono font-bold mt-0.5">{orderValue !== null ? `₹${orderValue.toLocaleString('en-IN')}` : 'Unavailable'}</p>
        </div>
      </div>

      {/* Risk score bar */}
      <div>
        <div className="flex items-center justify-between text-xs mb-1">
          <span className="muted-text">Risk Score</span>
          <span className="font-bold" style={{ color: riskColor }}>{riskScore}/100</span>
        </div>
        <div className="h-1.5 rounded-full" style={{ background: 'var(--surface-2)' }}>
          <div className="risk-bar-fill rounded-full" style={{ width: `${riskScore}%`, background: riskColor }} />
        </div>
        {draft.risk_reason && (
          <div className="flex items-start gap-1.5 mt-2 p-2 rounded" style={{ background: '#fbbf2415' }}>
            <AlertTriangle size={12} style={{ color: 'var(--warning)', marginTop: 2 }} />
            <span className="text-xs" style={{ color: 'var(--warning)' }}>{draft.risk_reason}</span>
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={handleApprove}
          disabled={loading || timeLeft === 0 || !hasValidQuote || !riskPassed}
          className="flex-1 py-2.5 rounded-lg font-semibold text-sm transition-all disabled:opacity-30 accent-glow"
          style={{ background: 'var(--accent)', color: '#000' }}
        >
          {loading ? 'Simulating…' : !riskPassed ? 'Risk checks failed' : !hasValidQuote ? 'Waiting for quote...' : 'Approve demo order'}
        </button>
        <button
          onClick={handleReject}
          disabled={loading}
          className="px-6 py-2.5 rounded-lg font-semibold text-sm transition-all"
          style={{ border: '1px solid var(--border)', color: 'var(--text-muted)' }}
        >
          Reject
        </button>
      </div>

      <p className="text-xs text-center muted-text">
        {!riskPassed
          ? 'This draft cannot be approved because it failed a configured risk check.'
          : `Click Approve to send this order to the simulated broker. No real trade will be placed. ${timeLeft}s remaining.`}
      </p>
    </div>
  )
}
