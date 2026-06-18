import { useEffect, useState } from 'react'
import { getHealth, type HealthResponse } from './api/client'
import { DeviceTable } from './components/DeviceTable'
import { DriftPanel } from './components/DriftPanel'
import { IpamTree } from './components/IpamTree'
import { TopologyMap } from './components/TopologyMap'

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  const netboxLabel = health
    ? health.netbox_configured
      ? 'configured'
      : 'not configured'
    : '…'

  return (
    <div className="app">
      <header>
        <h1>Argus</h1>
        <p className="tagline">The all-seeing keeper of your network&rsquo;s truth.</p>
        <span className={`badge ${health?.netbox_configured ? 'ok' : 'warn'}`}>
          NetBox: {netboxLabel}
        </span>
      </header>

      <main>
        <section>
          <h2>Devices</h2>
          <DeviceTable />
        </section>
        <section>
          <h2>IPAM</h2>
          <IpamTree />
        </section>
        <section>
          <h2>Drift</h2>
          <DriftPanel />
        </section>
        <section>
          <h2>Topology</h2>
          <TopologyMap />
        </section>
      </main>

      <footer>
        <span className="muted">Argus v{__APP_VERSION__} — NetBox is the source of truth.</span>
      </footer>
    </div>
  )
}
