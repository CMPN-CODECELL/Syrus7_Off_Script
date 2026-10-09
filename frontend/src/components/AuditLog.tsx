'use client'
import { useState, useEffect } from 'react'

export default function AuditLog() {
  const [entries, setEntries] = useState<any[]>([])
  const [narrative, setNarrative] = useState('')
  const [loadingAudit, setLoadingAudit] = useState(true)
  const [loadingNarrative, setLoadingNarrative] = useState(false)

  const fetchAudit = async () => {
    try {
      const res = await fetch('http://localhost:8000/audit/')
      const data = await res.json()
      setEntries(data.entries)
    } catch (e) {
      console.error('Failed to fetch audit log')
    } finally {
      setLoadingAudit(false)
    }
  }

  const fetchNarrative = async () => {
    setLoadingNarrative(true)
    try {
      const res = await fetch('http://localhost:8000/audit/narrative')
      const data = await res.json()
      setNarrative(data.narrative)
    } catch (e) {
      setNarrative('Failed to generate narrative.')
    } finally {
      setLoadingNarrative(false)
    }
  }

  useEffect(() => {
    fetchAudit()
    const timer = setInterval(fetchAudit, 10000) // Refresh every 10s
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <h2 className="text-lg font-bold mb-2">Audit Log & Trade Report</h2>
        <p className="text-xs muted-text mb-4">
          Immutable record of all system events. Every order, approval, and rule trigger is logged here.
        </p>
        <button
          onClick={fetchNarrative}
          disabled={loadingNarrative}
          className="px-4 py-2 rounded text-sm font-medium transition-all"
          style={{ background: 'var(--accent-dim)', color: 'var(--accent)' }}
        >
          {loadingNarrative ? 'Generating...' : 'Generate Daily Narrative Report'}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* Narrative section */}
        {narrative && (
          <div className="syrus-surface p-4">
            <h4 className="text-sm font-bold mb-2 accent-text">Today's Trade Summary</h4>
            <p className="text-sm leading-relaxed" style={{ color: 'var(--text)' }}>
              {narrative}
            </p>
          </div>
        )}

        {/* Audit entries */}
        <div>
          <h4 className="text-xs font-bold muted-text uppercase tracking-widest mb-2 px-1">Events</h4>
          {loadingAudit ? (
            <p className="text-xs muted-text">Loading...</p>
          ) : entries.length === 0 ? (
            <p className="text-xs muted-text text-center py-8">No events recorded yet.</p>
          ) : (
            <div className="space-y-2">
              {entries.map((entry: any, idx) => (
                <div key={idx} className="syrus-surface-2 p-3 text-xs font-mono">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <span className="accent-text font-bold">{entry.event_type}</span>
                      {entry.symbol && <span className="ml-2 muted-text">— {entry.symbol}</span>}
                    </div>
                    <span className="muted-text text-xs">
                      {new Date(entry.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  {entry.payload && (
                    <pre className="mt-1 text-xs overflow-x-auto p-1 rounded"
                         style={{ background: 'var(--bg)', color: 'var(--text-muted)' }}>
                      {JSON.stringify(entry.payload, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
