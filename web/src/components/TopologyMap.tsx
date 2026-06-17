import { useEffect, useMemo, useState } from 'react'
import { getTopology, type TopologyNode, type TopologyResponse } from '../api/client'
import { display } from '../format'

// Live topology from a discovery collector (default UniFi): devices grouped by site,
// colored by role, with uplink/neighbor edges drawn between them.

const ROLE_COLORS: Record<string, string> = {
  gateway: '#f1c40f',
  switch: '#4ea1ff',
  ap: '#2ecc71',
}

function roleColor(role: unknown): string {
  return ROLE_COLORS[display(role).toLowerCase()] ?? '#8b93a1'
}

const COL_W = 220
const ROW_H = 64
const NODE_W = 176
const NODE_H = 44
const HEADER_Y = 16
const FIRST_ROW_Y = HEADER_Y + NODE_H + 28

interface Placed {
  node: TopologyNode
  cx: number
  cy: number
  y: number
}

export function TopologyMap() {
  const [topo, setTopo] = useState<TopologyResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getTopology()
      .then((res) => (res.error ? setError(res.error) : setTopo(res)))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  const placed = useMemo(() => {
    const nodes = topo?.nodes ?? []
    const groups = new Map<string, TopologyNode[]>()
    for (const n of nodes) {
      const site = display(n.site)
      const list = groups.get(site) ?? []
      list.push(n)
      groups.set(site, list)
    }
    const sites = [...groups.entries()]
    const pos = new Map<string, Placed>()
    sites.forEach(([, list], si) => {
      list.forEach((node, di) => {
        const cx = si * COL_W + COL_W / 2
        const y = FIRST_ROW_Y + di * ROW_H
        pos.set(node.name, { node, cx, cy: y + NODE_H / 2, y })
      })
    })
    return { sites, pos }
  }, [topo])

  if (loading) return <p className="muted">Loading topology…</p>
  if (error) return <p className="muted">Topology unavailable: {error}</p>
  if (!topo || (topo.nodes ?? []).length === 0) return <p className="muted">No devices to map yet.</p>

  const { sites, pos } = placed
  const links = topo.links ?? []
  const maxRows = Math.max(...sites.map(([, list]) => list.length), 1)
  const width = Math.max(sites.length * COL_W, COL_W)
  const height = FIRST_ROW_Y + maxRows * ROW_H

  return (
    <div className="topology">
      <svg width={width} height={height} role="img" aria-label="Network topology">
        {/* edges first (behind nodes) */}
        {links.map((l, i) => {
          const a = pos.get(l.source)
          const b = pos.get(l.target)
          if (!a || !b) return null
          return (
            <line key={`e-${i}`} x1={a.cx} y1={a.cy} x2={b.cx} y2={b.cy} stroke="#4ea1ff" strokeOpacity="0.5" strokeWidth="2" />
          )
        })}
        {sites.map(([site, list], si) => {
          const cx = si * COL_W + COL_W / 2
          return (
            <g key={site}>
              <rect x={cx - NODE_W / 2} y={HEADER_Y} width={NODE_W} height={NODE_H} rx={6} fill="#20242d" stroke="#2a2f3a" />
              <text x={cx} y={HEADER_Y + 27} textAnchor="middle" fill="#e6e8eb" fontSize="13" fontWeight="600">
                {site}
              </text>
              {list.map((node) => {
                const p = pos.get(node.name)!
                return (
                  <g key={node.name}>
                    <rect x={cx - NODE_W / 2} y={p.y} width={NODE_W} height={NODE_H} rx={6} fill="#181b22" stroke={roleColor(node.role)} />
                    <text x={cx} y={p.y + 18} textAnchor="middle" fill="#e6e8eb" fontSize="12">
                      {display(node.name)}
                    </text>
                    <text x={cx} y={p.y + 34} textAnchor="middle" fill="#8b93a1" fontSize="10">
                      {display(node.primary_ip)}
                    </text>
                  </g>
                )
              })}
            </g>
          )
        })}
      </svg>
      <div className="legend">
        {Object.entries(ROLE_COLORS).map(([role, color]) => (
          <span key={role}>
            <i style={{ background: color }} /> {role}
          </span>
        ))}
        <span>
          <i style={{ background: '#8b93a1' }} /> other
        </span>
        {links.length > 0 && <span className="muted">— {links.length} link(s)</span>}
      </div>
    </div>
  )
}
