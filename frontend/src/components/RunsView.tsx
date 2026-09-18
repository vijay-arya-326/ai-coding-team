import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import { fetchThreadRuns, formatTimestamp } from '../api'
import type { RunRound, RunSummary, ThreadRuns } from '../types'

function formatDurationMs(ms: number | null): string {
  if (ms == null) return '—'
  const totalSec = Math.max(0, Math.round(ms / 1000))
  if (totalSec < 60) return `${totalSec}s`
  return `${Math.floor(totalSec / 60)}m ${totalSec % 60}s`
}

function formatTokens(n: number | null): string {
  return n == null ? '—' : n.toLocaleString()
}

function PreviewCell({
  text,
  label,
  onOpen,
}: {
  text: string | null
  label: string
  onOpen: (title: string, text: string) => void
}) {
  return (
    <button
      type="button"
      className="block w-full cursor-pointer text-left"
      onClick={() => text && onOpen(label, text)}
      title="Click to see full text"
    >
      <span className="line-clamp-3 break-words leading-snug text-slate-500">
        {text?.trim() || '—'}
      </span>
    </button>
  )
}

export default function RunsView({
  summaries,
  selectedId,
}: {
  summaries: RunSummary[]
  selectedId: string | null
}) {
  const [detail, setDetail] = useState<ThreadRuns | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [openRounds, setOpenRounds] = useState<Set<number>>(new Set())
  const [popup, setPopup] = useState<{ title: string; text: string } | null>(null)
  const [popupTab, setPopupTab] = useState<'raw' | 'parsed'>('raw')

  const openPopup = (title: string, text: string) => {
    setPopupTab('raw')
    setPopup({ title, text })
  }

  useEffect(() => {
    setDetail(null)
    setError(null)
    if (!selectedId) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    fetchThreadRuns(selectedId)
      .then((data) => {
        if (!cancelled) setDetail(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load runs')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedId])

  const toggleRound = (runIndex: number) => {
    setOpenRounds((prev) => {
      const next = new Set(prev)
      if (next.has(runIndex)) next.delete(runIndex)
      else next.add(runIndex)
      return next
    })
  }

  const totals = summaries.reduce(
    (acc, s) => ({
      input: acc.input + s.total_input_tokens,
      output: acc.output + s.total_output_tokens,
      total: acc.total + s.total_tokens,
      tools: acc.tools + s.tool_count,
    }),
    { input: 0, output: 0, total: 0, tools: 0 },
  )

  return (
    <div className="flex min-w-0 flex-1 flex-col bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3.5">
        <div>
          <h1 className="text-[15px] font-semibold text-slate-900">Runs · Model tracing</h1>
          <p className="mt-0.5 text-xs text-slate-500">
            Token usage and tool communication summarised per conversation
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-indigo-700">
            ⇣ Input {formatTokens(totals.input)}
          </span>
          <span className="rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-indigo-700">
            ⇡ Output {formatTokens(totals.output)}
          </span>
          <span className="rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-indigo-700">
            Σ {formatTokens(totals.total)} tokens
          </span>
          <span className="rounded-full border border-indigo-100 bg-indigo-50 px-3 py-1 text-indigo-700">
            {totals.tools} tool calls
          </span>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-5">
        {selectedId && loading && <p className="text-sm text-slate-500">Loading trace…</p>}
        {selectedId && !loading && error && <p className="text-sm text-red-600">{error}</p>}
        {!selectedId && summaries.length === 0 && (
          <p className="text-sm text-slate-500">
            No runs yet. Send a message in chat to start tracing token usage.
          </p>
        )}

            {selectedId && !loading && !error && detail && (
              <div className="mt-5 overflow-hidden rounded-xl border border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div className="text-[13px] font-semibold text-slate-800">
                    {detail.title ?? 'Conversation'} · runs
                  </div>
                  <div className="flex gap-2 text-[11.5px] text-slate-500">
                    <span>⇣ {formatTokens(detail.totals.input_tokens)}</span>
                    <span>⇡ {formatTokens(detail.totals.output_tokens)}</span>
                    <span className="font-semibold text-indigo-700">
                      Σ {formatTokens(detail.totals.total_tokens)}
                    </span>
                    <span className="text-slate-400">·</span>
                    <span>avg {formatDurationMs(detail.totals.avg_duration_ms)}</span>
                  </div>
                </div>

                <table className="w-full table-fixed border-collapse text-[12.5px]">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                      <th className="w-8 px-3 py-2.5" />
                      <th className="w-16 px-2 py-2.5">Time</th>
                      <th className="w-14 px-2 py-2.5">Round</th>
                      <th className="w-2/5 px-2 py-2.5">Input (context)</th>
                      <th className="w-2/5 px-2 py-2.5">Output (completion)</th>
                      <th className="w-28 px-2 py-2.5">Tools</th>
                      <th className="w-12 px-2 py-2.5 text-right">In</th>
                      <th className="w-12 px-2 py-2.5 text-right">Out</th>
                      <th className="w-14 px-2 py-2.5 text-right">Tot</th>
                      <th className="w-16 px-3 py-2.5 text-right">Dur</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.runs.map((r) => (
                      <RoundRow
                        key={r.run_index}
                        round={r}
                        open={openRounds.has(r.run_index)}
                        onToggle={() => toggleRound(r.run_index)}
                        onOpen={(title, text) => openPopup(title, text)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
      </div>

      {popup && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-6"
          onClick={() => setPopup(null)}
        >
          <div
            className="w-full max-w-3xl overflow-hidden rounded-xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <div className="truncate text-[13px] font-semibold text-slate-800">
                {popup.title}
              </div>
              <button
                type="button"
                className="cursor-pointer rounded-md px-2 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                onClick={() => setPopup(null)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            <div className="flex gap-1 border-b border-slate-100 px-4 pt-2.5">
              {(['raw', 'parsed'] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setPopupTab(tab)}
                  className={`cursor-pointer rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                    popupTab === tab
                      ? 'bg-indigo-50 text-indigo-700'
                      : 'text-slate-400 hover:text-slate-600'
                  }`}
                >
                  {tab === 'raw' ? 'Raw Output' : 'Parsed Output'}
                </button>
              ))}
            </div>
            <div className="max-h-[60vh] overflow-y-auto p-4">
              {popupTab === 'parsed' ? (
                <div className="markdown text-[13.5px] text-slate-800">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeRaw, rehypeSanitize]}
                  >
                    {popup.text}
                  </ReactMarkdown>
                </div>
              ) : (
                <pre className="break-words whitespace-pre-wrap font-mono text-[12.5px] leading-relaxed text-slate-700">
                  {popup.text}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function RoundRow({
  round,
  open,
  onToggle,
  onOpen,
}: {
  round: RunRound
  open: boolean
  onToggle: () => void
  onOpen: (title: string, text: string) => void
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer border-b border-slate-100 hover:bg-indigo-50/40"
      >
        <td className="px-3 py-2.5 text-indigo-500">
          <span className={`inline-block transition-transform ${open ? 'rotate-90' : ''}`}>
            ▶
          </span>
        </td>
        <td className="px-2 py-2.5 text-slate-500">{formatTimestamp(round.started_at) || '—'}</td>
        <td className="px-2 py-2.5 font-mono text-slate-600">r{round.run_index}</td>
        <td className="px-2 py-2.5">
          <PreviewCell text={round.input_preview} label={`Round r${round.run_index} · input`} onOpen={onOpen} />
        </td>
        <td className="px-2 py-2.5">
          <PreviewCell text={round.output_preview} label={`Round r${round.run_index} · output`} onOpen={onOpen} />
        </td>
        <td className="px-2 py-2.5">
          {round.tools.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {round.tools.map((t, i) => (
                <span
                  key={i}
                  className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-700"
                >
                  {t.name ?? 'tool'}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-slate-300">—</span>
          )}
        </td>
        <td className="px-2 py-2.5 text-right font-mono text-slate-400">
          {formatTokens(round.input_tokens)}
        </td>
        <td className="px-2 py-2.5 text-right font-mono text-slate-400">
          {formatTokens(round.output_tokens)}
        </td>
        <td className="px-2 py-2.5 text-right font-mono font-semibold text-indigo-700">
          {formatTokens(round.total_tokens)}
        </td>
        <td className="px-3 py-2.5 text-right font-mono text-slate-500">
          {formatDurationMs(round.duration_ms)}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-slate-100 bg-slate-50/70">
          <td colSpan={10} className="px-4 py-3">
            {round.tools.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {round.tools.map((t, i) => (
                  <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
                    <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                      tool · {t.name ?? 'unknown'}
                    </div>
                    <div className="mb-2">
                      <div className="mb-0.5 text-[10px] uppercase tracking-wider text-slate-400">
                        input (arguments)
                      </div>
                      <button
                        type="button"
                        className="block w-full cursor-pointer text-left"
                        onClick={() => t.input && onOpen(`tool ${t.name ?? ''} · input`, t.input)}
                        title="Click to see full text"
                      >
                        <pre className="line-clamp-3 break-words whitespace-pre-wrap font-mono text-[11.5px] text-slate-700">
                          {t.input || '—'}
                        </pre>
                      </button>
                    </div>
                    <div>
                      <div className="mb-0.5 text-[10px] uppercase tracking-wider text-slate-400">
                        output (result)
                      </div>
                      <button
                        type="button"
                        className="block w-full cursor-pointer text-left"
                        onClick={() => t.output && onOpen(`tool ${t.name ?? ''} · output`, t.output)}
                        title="Click to see full text"
                      >
                        <pre className="line-clamp-3 break-words whitespace-pre-wrap font-mono text-[11.5px] text-slate-700">
                          {t.output || '—'}
                        </pre>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">No tool calls in this round.</p>
            )}
          </td>
        </tr>
      )}
    </>
  )
}