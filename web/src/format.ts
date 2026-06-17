// Render an arbitrary NetBox field value (scalar, or a nested FK object with
// display/name/slug) as a short human string.
export function display(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>
    return String(obj.display ?? obj.name ?? obj.value ?? JSON.stringify(value))
  }
  return String(value)
}
