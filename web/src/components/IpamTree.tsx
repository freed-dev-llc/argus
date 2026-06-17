import { useEffect, useMemo, useState } from 'react'
import { getPrefixes, type Prefix } from '../api/client'
import { display } from '../format'
import { buildPrefixTree, type PrefixNode } from '../ipam'

function Rows({ node, depth }: { node: PrefixNode; depth: number }) {
  const status = display(node.data.status)
  const desc = display(node.data.description)
  return (
    <>
      <li style={{ paddingLeft: depth * 18 }}>
        <code>{node.cidr}</code>
        {status !== '—' && <span className="badge">{status}</span>}
        {desc !== '—' && <span className="muted"> {desc}</span>}
      </li>
      {node.children.map((child) => (
        <Rows key={child.cidr} node={child} depth={depth + 1} />
      ))}
    </>
  )
}

export function IpamTree() {
  const [prefixes, setPrefixes] = useState<Prefix[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getPrefixes()
      .then((res) => (res.error ? setError(res.error) : setPrefixes(res.prefixes ?? [])))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  const roots = useMemo(() => buildPrefixTree(prefixes), [prefixes])

  if (loading) return <p className="muted">Loading prefixes…</p>
  if (error) return <p className="muted">IPAM unavailable: {error}</p>
  if (prefixes.length === 0) return <p className="muted">No prefixes in NetBox yet.</p>

  return (
    <ul className="prefix-tree">
      {roots.map((root) => (
        <Rows key={root.cidr} node={root} depth={0} />
      ))}
    </ul>
  )
}
