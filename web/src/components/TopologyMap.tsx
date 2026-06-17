import { useEffect, useMemo, useState } from 'react'
import { getDevices, type Device } from '../api/client'
import { display } from '../format'

// First-cut topology: devices grouped by site, colored by role. Real link edges
// (cabling / LLDP neighbors) layer on once a collector provides neighbor data (#8);
// a graph library (react-flow / cytoscape) is only worth its weight at that point.

const ROLE_COLORS: Record<string, string> = {
  gateway: '#f1c40f',
  switch: '#4ea1ff',
  ap: '#2ecc71',
}

function roleColor(role: string): string {
  return ROLE_COLORS[role.toLowerCase()] ?? '#8b93a1'
}

const COL_W = 220
const ROW_H = 64
const NODE_W = 176
const NODE_H = 44
const HEADER_Y = 16
const FIRST_ROW_Y = HEADER_Y + NODE_H + 28

export function TopologyMap() {
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDevices()
      .then((res) => (res.error ? setError(res.error) : setDevices(res.devices ?? [])))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  const sites = useMemo(() => {
    const groups = new Map<string, Device[]>()
    for (const d of devices) {
      const site = display(d.site)
      const list = groups.get(site) ?? []
      list.push(d)
      groups.set(site, list)
    }
    return [...groups.entries()]
  }, [devices])

  if (loading) return <p className="muted">Loading topology…</p>
  if (error) return <p className="muted">Topology unavailable: {error}</p>
  if (devices.length === 0) return <p className="muted">No devices to map yet.</p>

  const maxRows = Math.max(...sites.map(([, list]) => list.length), 1)
  const width = Math.max(sites.length * COL_W, COL_W)
  const height = FIRST_ROW_Y + maxRows * ROW_H

  return (
    <div className="topology">
      <svg width={width} height={height} role="img" aria-label="Network topology by site">
        {sites.map(([site, list], si) => {
          const cx = si * COL_W + COL_W / 2
          return (
            <g key={site}>
              <rect
                x={cx - NODE_W / 2}
                y={HEADER_Y}
                width={NODE_W}
                height={NODE_H}
                rx={6}
                fill="#20242d"
                stroke="#2a2f3a"
              />
              <text x={cx} y={HEADER_Y + 27} textAnchor="middle" fill="#e6e8eb" fontSize="13" fontWeight="600">
                {site}
              </text>
              {list.map((d, di) => {
                const dy = FIRST_ROW_Y + di * ROW_H
                const color = roleColor(display(d.role))
                return (
                  <g key={`${site}-${di}`}>
                    <line x1={cx} y1={HEADER_Y + NODE_H} x2={cx} y2={dy} stroke="#2a2f3a" />
                    <rect
                      x={cx - NODE_W / 2}
                      y={dy}
                      width={NODE_W}
                      height={NODE_H}
                      rx={6}
                      fill="#181b22"
                      stroke={color}
                    />
                    <text x={cx} y={dy + 18} textAnchor="middle" fill="#e6e8eb" fontSize="12">
                      {display(d.name)}
                    </text>
                    <text x={cx} y={dy + 34} textAnchor="middle" fill="#8b93a1" fontSize="10">
                      {display(d.primary_ip)}
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
      </div>
    </div>
  )
}
