import { formatTimestamp } from '../api'
import type { RunSummary } from '../types'

interface RunsListProps {
  summaries: RunSummary[]
  selectedId: string | null
  loading: boolean
  onSelect: (threadId: string) => void
}

function formatTokens(n: number | null): string {
  if (n == null || Number.isNaN(n)) return '0'
  return Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n)
}

export default function RunsList({ summaries, selectedId, loading, onSelect }: RunsListProps) {
  return (
    <>
      {loading && <p className="p-3 text-[13px] text-slate-400">Loading runs…</p>}
      {!loading && summaries.length === 0 && (
        <p className="p-3 text-[13px] leading-relaxed text-slate-400">
          No runs yet. Send a message in chat to start tracing token usage.
        </p>
      )}
      {summaries.map((s, i) => {
        const selected = selectedId === s.thread_id
        return (
          <div
            key={s.thread_id}
            className={`mb-1 rounded-lg ${
              selected
                ? 'bg-indigo-500/20 ring-1 ring-indigo-400/50'
                : i % 2 === 0
                  ? 'bg-white/[0.03]'
                  : 'bg-white/[0.08]'
            }`}
          >
            <button
              onClick={() => onSelect(s.thread_id)}
              className="flex w-full cursor-pointer flex-col gap-1.5 rounded-lg p-2.5 text-left"
              title={s.thread_id}
            >
              <span className="line-clamp-3 break-words rounded-[14px] rounded-bl-[4px] border border-white/10 bg-indigo-500/15 px-3 py-2 text-[12.5px] leading-snug text-slate-100">
                {s.title ?? 'Untitled conversation'}
              </span>
              <span className="flex items-center justify-between gap-2 text-[11px] text-slate-400">
                <span className="truncate">
                  {s.run_count} round{s.run_count === 1 ? '' : 's'} ·{' '}
                  {formatTimestamp(s.last_run_at) || 'recently'}
                </span>
                <span className="font-mono shrink-0">
                  {formatTokens(s.total_tokens)} tok
                  {s.tool_count > 0 ? ` · ${s.tool_count} ⚙` : ''}
                </span>
              </span>
            </button>
          </div>
        )
      })}
    </>
  )
}