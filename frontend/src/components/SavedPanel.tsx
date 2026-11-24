import type { SavedScenario } from '../types'
import { Button } from './controls'

export function SavedPanel({
  saved,
  activeId,
  onOpen,
  onDelete,
}: {
  saved: SavedScenario[]
  activeId: string | null
  onOpen: (s: SavedScenario) => void
  onDelete: (s: SavedScenario) => void
}) {
  if (saved.length === 0) {
    return <p className="rounded-xl border border-dashed border-line bg-white p-8 text-center text-sm text-slate-500">No saved scenarios yet. Build one on the Estimate tab and press Save.</p>
  }
  return (
    <ul className="space-y-3">
      {saved.map((s) => (
        <li key={s.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-white p-4 shadow-sm">
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">
              {s.name} {s.id === activeId && <span className="ml-1 rounded bg-slate-100 px-1.5 text-xs font-normal">open</span>}
            </p>
            <p className="text-xs text-slate-500">
              {s.scenario.items.length} item(s) · updated {new Date(s.updated_at).toLocaleString()}
            </p>
          </div>
          <Button onClick={() => onOpen(s)}>Open</Button>
          <Button variant="danger" onClick={() => onDelete(s)}>
            Delete
          </Button>
        </li>
      ))}
    </ul>
  )
}
