import { useCallback, useEffect, useState } from 'react'
import {
  getDrift,
  postReconcile,
  type Change,
  type DriftResponse,
  type ReconcileResponse,
} from '../api/client'

function fmt(value: unknown): string {
  if (value == null) return '∅'
  return String(value)
}

function summarizeDetails(details: Record<string, unknown>): string {
  return Object.entries(details)
    .filter(([key]) => key !== 'name')
    .map(([key, value]) => {
      if (value && typeof value === 'object' && 'desired' in (value as object)) {
        const delta = value as { current?: unknown; desired?: unknown }
        return `${key}: ${fmt(delta.current)} → ${fmt(delta.desired)}`
      }
      return `${key}=${fmt(value)}`
    })
    .join(', ')
}

function ChangeRow({ change }: { change: Change }) {
  return (
    <li>
      <span className={`badge action-${change.action}`}>{change.action}</span>{' '}
      <strong>{change.identifier}</strong>
      {Object.keys(change.details).length > 1 || change.action === 'update' ? (
        <span className="muted"> — {summarizeDetails(change.details)}</span>
      ) : null}
    </li>
  )
}

export function DriftPanel() {
  const [drift, setDrift] = useState<DriftResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [plan, setPlan] = useState<ReconcileResponse | null>(null)
  const [result, setResult] = useState<ReconcileResponse | null>(null)
  const [busy, setBusy] = useState(false)

  const loadDrift = useCallback(() => {
    setLoading(true)
    setPlan(null)
    setResult(null)
    setError(null)
    getDrift()
      .then(setDrift)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    // Fetch drift on mount. loadDrift() resets to the loading state before an
    // async fetch — a legitimate "synchronize with an external system" effect
    // that react-hooks v7's set-state-in-effect rule false-positives on.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadDrift()
  }, [loadDrift])

  const planApply = () => {
    setBusy(true)
    postReconcile()
      .then((res) => (res.error ? setError(res.error) : setPlan(res)))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  const confirmApply = (token: string) => {
    setBusy(true)
    postReconcile(token)
      .then((res) => {
        setResult(res)
        setPlan(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  if (loading) return <p className="muted">Loading drift…</p>
  if (error) return <p className="muted">Drift unavailable: {error}</p>
  if (drift?.error) return <p className="muted">{drift.error}</p>
  if (!drift) return <p className="muted">No drift data.</p>

  const changes = drift.changes ?? []
  const total = drift.summary?.total ?? 0

  return (
    <div className="drift">
      <p>
        <strong>{total}</strong> proposed change{total === 1 ? '' : 's'}
        {drift.collector ? ` from ${drift.collector}` : ''} (dry-run).{' '}
        <button onClick={loadDrift} disabled={busy}>
          Re-scan
        </button>
      </p>

      {changes.length > 0 && (
        <ul className="changes">
          {changes.map((c, i) => (
            <ChangeRow key={`${c.identifier}-${i}`} change={c} />
          ))}
        </ul>
      )}

      {drift.notes?.map((note, i) => (
        <p key={i} className="muted">
          {note}
        </p>
      ))}

      {/* apply flow */}
      {result ? (
        <div className="apply-result">
          <p>
            Applied {result.applied_count ?? 0} / {result.results?.length ?? 0} change(s).
          </p>
          <ul className="changes">
            {result.results?.map((r, i) => (
              <li key={i}>
                <span className={`badge status-${r.status}`}>{r.status}</span>{' '}
                <strong>{r.identifier}</strong>
                {r.detail ? <span className="muted"> — {fmt(r.detail)}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : plan?.confirm_token ? (
        <div className="apply-confirm">
          <p className="muted">{plan.message}</p>
          <button onClick={() => confirmApply(plan.confirm_token as string)} disabled={busy}>
            Confirm apply ({plan.summary?.total ?? 0})
          </button>{' '}
          <button onClick={() => setPlan(null)} disabled={busy}>
            Cancel
          </button>
        </div>
      ) : (
        changes.length > 0 && (
          <button onClick={planApply} disabled={busy}>
            {busy ? 'Working…' : 'Plan apply…'}
          </button>
        )
      )}
    </div>
  )
}
