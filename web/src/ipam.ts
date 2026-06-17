import { type Prefix } from './api/client'

// Build a containment tree from a flat list of NetBox prefixes. IPv4 prefixes nest by
// CIDR containment; IPv6 (and anything unparseable) become flat roots for now.

export interface PrefixNode {
  cidr: string
  data: Prefix
  children: PrefixNode[]
}

interface V4 {
  base: number
  len: number
}

function parseV4(cidr: string): V4 | null {
  const slash = cidr.indexOf('/')
  if (slash < 0) return null
  const addr = cidr.slice(0, slash)
  if (addr.includes(':')) return null // IPv6
  const octets = addr.split('.')
  if (octets.length !== 4) return null
  let base = 0
  for (const octet of octets) {
    const n = Number(octet)
    if (!Number.isInteger(n) || n < 0 || n > 255) return null
    base = (base << 8) + n
  }
  const len = Number(cidr.slice(slash + 1))
  if (!Number.isInteger(len) || len < 0 || len > 32) return null
  return { base: base >>> 0, len }
}

function maskOf(len: number): number {
  return len === 0 ? 0 : (0xffffffff << (32 - len)) >>> 0
}

function contains(parent: V4, child: V4): boolean {
  if (parent.len > child.len) return false
  return ((child.base & maskOf(parent.len)) >>> 0) === parent.base
}

interface Item {
  cidr: string
  prefix: Prefix
  v4: V4 | null
}

export function buildPrefixTree(prefixes: Prefix[]): PrefixNode[] {
  const items: Item[] = prefixes
    .filter((p): p is Prefix & { prefix: string } => typeof p.prefix === 'string')
    .map((p) => ({ cidr: p.prefix, prefix: p, v4: parseV4(p.prefix) }))

  // Broadest (shortest len) first so a node's parent is always already placed.
  // Unparseable / IPv6 sort last and stay as roots.
  items.sort((a, b) => {
    if (a.v4 && b.v4) return a.v4.len - b.v4.len || a.v4.base - b.v4.base
    if (a.v4) return -1
    if (b.v4) return 1
    return a.cidr.localeCompare(b.cidr)
  })

  const roots: PrefixNode[] = []
  const placed: { v4: V4; node: PrefixNode }[] = []

  for (const item of items) {
    const node: PrefixNode = { cidr: item.cidr, data: item.prefix, children: [] }
    let parent: PrefixNode | null = null

    if (item.v4) {
      let bestLen = -1
      for (const candidate of placed) {
        const c = candidate.v4
        const sameNet = c.len === item.v4.len && c.base === item.v4.base
        if (!sameNet && contains(c, item.v4) && c.len > bestLen) {
          bestLen = c.len
          parent = candidate.node
        }
      }
      placed.push({ v4: item.v4, node })
    }

    if (parent) parent.children.push(node)
    else roots.push(node)
  }

  return roots
}
