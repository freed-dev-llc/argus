import { useEffect, useState } from 'react'
import { askBrain, getCollectors, type AskResponse, type AskSource } from '../api/client'

function dedupeSources(sources: AskSource[]): AskSource[] {
  const seen = new Set<string>()
  return sources.filter((s) => {
    const key = `${s.title ?? ''}|${s.source ?? ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function SourceItem({ source }: { source: AskSource }) {
  const label = source.title || source.source || 'source'
  const page = source.page ? ` (p.${source.page})` : ''
  const isLink = source.source?.startsWith('http')
  return (
    <li className="muted">
      {isLink ? (
        <a href={source.source} target="_blank" rel="noreferrer">
          {label}
        </a>
      ) : (
        label
      )}
      {page}
    </li>
  )
}

export function AskBrainPanel() {
  const [question, setQuestion] = useState('')
  const [resp, setResp] = useState<AskResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [packs, setPacks] = useState<string[]>([])
  const [pack, setPack] = useState('')

  // Discover which Mnemosyne knowledge pack(s) the discovered vendors map to, so the panel
  // asks the right pack instead of a hardcoded one (ADR-0013). On any failure it leaves the
  // list empty and ask() falls back to the askBrain default.
  useEffect(() => {
    getCollectors()
      .then((res) => {
        const found = Array.from(
          new Set(
            (res.collectors ?? [])
              .map((c) => c.knowledge_pack)
              .filter((p): p is string => Boolean(p)),
          ),
        )
        setPacks(found)
        if (found.length > 0) setPack(found[0])
      })
      .catch(() => {
        /* no collectors / unreachable — ask() uses the askBrain default */
      })
  }, [])

  const ask = () => {
    const q = question.trim()
    if (!q || busy) return
    setBusy(true)
    setError(null)
    setResp(null)
    ;(pack ? askBrain(q, pack) : askBrain(q))
      .then(setResp)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  const sources = resp?.sources ? dedupeSources(resp.sources) : []

  return (
    <div className="ask-brain">
      <p className="muted">
        Ask the knowledge brain (Mnemosyne) about your network — answered from the docs it has
        ingested, with citations. Argus discovers; Mnemosyne explains.
      </p>

      <form
        className="ask-form"
        onSubmit={(e) => {
          e.preventDefault()
          ask()
        }}
      >
        {packs.length > 1 && (
          <select
            value={pack}
            onChange={(e) => setPack(e.target.value)}
            disabled={busy}
            aria-label="Knowledge pack"
          >
            {packs.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        )}
        <input
          type="text"
          value={question}
          placeholder="e.g. How do I adopt a UniFi switch to a remote controller?"
          onChange={(e) => setQuestion(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !question.trim()}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {error && <p className="muted">Brain unavailable: {error}</p>}
      {resp?.error && <p className="muted">{resp.error}</p>}

      {resp?.answer && (
        <div className="ask-response">
          <p className="ask-answer">{resp.answer}</p>
          {sources.length > 0 && (
            <ul className="ask-sources">
              {sources.map((s, i) => (
                <SourceItem key={i} source={s} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
