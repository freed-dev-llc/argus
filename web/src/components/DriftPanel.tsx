import { useEffect, useState } from 'react'
import { getDrift, type DriftResponse } from '../api/client'

export function DriftPanel() {
  const [drift, setDrift] = useState<DriftResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getDrift()
      .then(setDrift)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error) return <p className="muted">Drift unavailable: {error}</p>
  if (!drift) return <p className="muted">Loading drift…</p>

  const total = drift.summary?.total ?? 0

  return (
    <div>
      <p>
        <strong>{total}</strong> pending change{total === 1 ? '' : 's'}
        {drift.summary?.dry_run ? ' (dry-run)' : ''}.
      </p>
      {drift.notes?.map((note, i) => (
        <p key={i} className="muted">
          {note}
        </p>
      ))}
    </div>
  )
}
