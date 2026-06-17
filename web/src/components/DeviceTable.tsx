import { useEffect, useState } from 'react'
import { getDevices, type Device } from '../api/client'
import { display } from '../format'

export function DeviceTable() {
  const [devices, setDevices] = useState<Device[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDevices()
      .then((res) => {
        if (res.error) setError(res.error)
        else setDevices(res.devices ?? [])
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="muted">Loading devices…</p>
  if (error) return <p className="muted">Devices unavailable: {error}</p>
  if (devices.length === 0) return <p className="muted">No devices in NetBox yet.</p>

  return (
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Status</th>
          <th>Site</th>
        </tr>
      </thead>
      <tbody>
        {devices.map((d, i) => (
          <tr key={d.id ?? i}>
            <td>{display(d.name)}</td>
            <td>{display(d.status)}</td>
            <td>{display(d.site)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
