import type { ThreadSummary } from '../types'

interface SidebarProps {
  threads: ThreadSummary[]
  activeId: string | null
  disabled: boolean
  onSelect: (threadId: string) => void
  onNew: () => void
  onDelete: (threadId: string) => void
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const now = Date.now()
  const diff = now - date.getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return date.toLocaleDateString()
}

export default function Sidebar({
  threads,
  activeId,
  disabled,
  onSelect,
  onNew,
  onDelete,
}: SidebarProps) {
  return (
    <aside className="flex w-75 shrink-0 flex-col bg-[#1f2430] text-slate-200">
      <div className="flex flex-col gap-3 border-b border-white/10 px-4 pb-3 pt-5">
        <h1 className="text-lg font-semibold text-white">Agent Chat</h1>
        <button
          className="cursor-pointer rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          onClick={onNew}
          disabled={disabled}
          title="Start a new conversation"
        >
          + New chat
        </button>
      </div>

      <nav className="sidebar-scroll flex-1 overflow-y-auto p-2">
        {threads.length === 0 && (
          <p className="p-3 text-[13px] leading-relaxed text-slate-400">
            No conversations yet. Send a message to start one.
          </p>
        )}
        {threads.map((thread) => (
          <div
            key={thread.thread_id}
            className={`mb-0.5 flex items-center gap-1 rounded-lg ${
              activeId === thread.thread_id ? 'bg-indigo-500/20' : ''
            }`}
          >
            <button
              className="flex min-w-0 flex-1 cursor-pointer flex-col gap-1 rounded-lg p-2.5 text-left text-sm hover:bg-white/5 disabled:cursor-wait"
              onClick={() => onSelect(thread.thread_id)}
              disabled={disabled}
              title={thread.thread_id}
            >
              <span className="truncate text-slate-100">
                {thread.last_message?.content ?? 'New conversation'}
              </span>
              <span className="text-xs text-slate-400">
                {thread.message_count} messages · {formatTime(thread.updated_at)}
              </span>
            </button>
            <button
              className="cursor-pointer rounded-md px-2.5 py-1.5 text-lg leading-none text-slate-400 hover:bg-white/5 hover:text-red-400 disabled:cursor-wait"
              onClick={() => onDelete(thread.thread_id)}
              disabled={disabled}
              title="Delete this thread"
              aria-label="Delete thread"
            >
              ×
            </button>
          </div>
        ))}
      </nav>
    </aside>
  )
}