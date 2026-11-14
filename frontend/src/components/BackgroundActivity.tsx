import { useState } from 'react'
import type { BackgroundActivity as BackgroundActivityItem } from '../types'

interface BackgroundActivityProps {
  activity: BackgroundActivityItem | null
  loading: boolean
  onUpdate: (update: Partial<Pick<BackgroundActivityItem, 'detail' | 'completed'>>) => void
}

export default function BackgroundActivity({ activity, loading, onUpdate }: BackgroundActivityProps) {
  const [draftDetail, setDraftDetail] = useState<string | null>(null)
  const detail = draftDetail ?? activity?.detail ?? ''

  const save = () => {
    const nextDetail = detail.trim()
    if (nextDetail && nextDetail !== activity?.detail) onUpdate({ detail: nextDetail })
    setDraftDetail(null)
  }

  return (
    <aside className="hidden w-72 shrink-0 border-l border-slate-200 bg-white p-5 lg:flex lg:flex-col">
      <div className="mb-5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Shared todo</p>
        <h2 className="mt-1 text-base font-semibold text-slate-800">Background activity</h2>
      </div>
      {loading ? (
        <div aria-busy="true" className="h-20 animate-pulse rounded-lg bg-slate-100" />
      ) : activity ? (
        <div className="rounded-lg border border-slate-200 p-3">
          <label className="flex cursor-pointer items-start gap-2.5">
            <input
              type="checkbox"
              checked={activity.completed}
              onChange={(event) => onUpdate({ completed: event.target.checked })}
              className="mt-0.5 h-4 w-4 accent-emerald-600"
            />
            <span className="text-sm font-medium text-slate-700">Shared agent activity</span>
          </label>
          <textarea
            aria-label="Background activity detail"
            value={detail}
            maxLength={240}
            rows={4}
            onBlur={save}
            onChange={(event) => setDraftDetail(event.target.value)}
            className={`mt-3 w-full resize-none rounded-md border border-slate-200 bg-slate-50 p-2 text-sm leading-5 text-slate-700 outline-none focus:border-indigo-400 ${activity.completed ? 'line-through text-slate-400' : ''}`}
          />
          <p className="mt-2 text-[11px] text-slate-400">
            {activity.completed ? 'Completed' : 'In progress'}{activity.updated_by ? ` · ${activity.updated_by}` : ''}
          </p>
        </div>
      ) : (
        <p role="status" className="text-sm text-slate-500">Couldn’t load background activity.</p>
      )}
    </aside>
  )
}
