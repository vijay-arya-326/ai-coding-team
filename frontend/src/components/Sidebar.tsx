import { formatTimestamp } from '../api'
import type { RunSummary, ThreadSummary, Workspace } from '../types'
import RunsList from './RunsList'
import WorkspaceSelector from './WorkspaceSelector'

interface SidebarProps {
  threads: ThreadSummary[]
  activeId: string | null
  disabled: boolean
  showArchived: boolean
  view: 'chat' | 'runs' | 'workspaces'
  runs: RunSummary[]
  runsLoading: boolean
  selectedRunId: string | null
  workspaces: Workspace[]
  onViewChange: (view: 'chat' | 'runs' | 'workspaces') => void
  onSelectRun: (threadId: string) => void
  onToggleArchived: () => void
  onSelect: (threadId: string) => void
  onNew: () => void
  onRename: (threadId: string) => void
  onArchive: (threadId: string) => void
  onDelete: (threadId: string) => void
  onWorkspaceChange: (workspaceId: string) => void
}

function threadLabel(t: ThreadSummary): string {
  return t.title ?? t.first_user_message ?? 'New conversation'
}

function PenIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z" />
    </svg>
  )
}

function ArchiveIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8" />
      <path d="M10 13h4" />
    </svg>
  )
}

export default function Sidebar({
  threads,
  activeId,
  disabled,
  showArchived,
  view,
  runs,
  runsLoading,
  selectedRunId,
  workspaces,
  onViewChange,
  onSelectRun,
  onToggleArchived,
  onSelect,
  onNew,
  onRename,
  onArchive,
  onDelete,
  onWorkspaceChange,
}: SidebarProps) {
  const activeWsId = workspaces.find((w) => w.active)?.id ?? 'default'
  const visible = threads.filter(
    (t) => (t.workspace_id ?? 'default') === activeWsId && t.archived === showArchived,
  )
  const hasOtherWsThreads = threads.some(
    (t) => (t.workspace_id ?? 'default') !== activeWsId,
  )
  const activeCount = visible.filter((t) => !t.archived).length
  const archivedCount = visible.length - activeCount

  return (
    <aside className="flex w-80 shrink-0 flex-col bg-[#1f2430] text-slate-200">
      <div className="flex flex-col gap-3 border-b border-white/10 px-4 pb-3 pt-5">
        <h1 className="text-lg font-semibold text-white">Agent Chat</h1>
        <div className="flex gap-1.5">
          <button
            className={`flex-1 cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
              view === 'chat'
                ? 'bg-indigo-500/25 text-white'
                : 'text-slate-300 hover:bg-white/5'
            }`}
            onClick={() => onViewChange('chat')}
          >
            💬 Chat
          </button>
          <button
            className={`flex-1 cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
              view === 'runs'
                ? 'bg-indigo-500/25 text-white'
                : 'text-slate-300 hover:bg-white/5'
            }`}
            onClick={() => onViewChange('runs')}
          >
            ▤ Runs
          </button>
          <button
            className={`flex-1 cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
              view === 'workspaces'
                ? 'bg-indigo-500/25 text-white'
                : 'text-slate-300 hover:bg-white/5'
            }`}
            onClick={() => onViewChange('workspaces')}
          >
            ▦ Spaces
          </button>
        </div>
        {view !== 'workspaces' && (
          <WorkspaceSelector
            workspaces={workspaces}
            activeId={workspaces.find((w) => w.active)?.id ?? activeId}
            disabled={disabled}
            onChange={onWorkspaceChange}
          />
        )}
        <button
          className="cursor-pointer rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          onClick={onNew}
          disabled={disabled}
          title="Start a new conversation"
        >
          + New chat
        </button>
        {view === 'chat' && (
          <div className="flex gap-1.5">
            <button
              className={`flex-1 cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                !showArchived
                  ? 'bg-indigo-500/25 text-white'
                  : 'text-slate-300 hover:bg-white/5'
              }`}
              onClick={() => showArchived && onToggleArchived()}
            >
              Active · {activeCount}
            </button>
            <button
              className={`flex-1 cursor-pointer rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
                showArchived
                  ? 'bg-indigo-500/25 text-white'
                  : 'text-slate-300 hover:bg-white/5'
              }`}
              onClick={() => !showArchived && onToggleArchived()}
            >
              Archived · {archivedCount}
            </button>
          </div>
        )}
      </div>

      <nav className="sidebar-scroll flex-1 overflow-y-auto p-2">
      {view === 'runs' ? (
          <RunsList
            summaries={runs}
            selectedId={selectedRunId}
            loading={runsLoading}
            onSelect={onSelectRun}
          />
        ) : view === 'workspaces' ? (
          <p className="p-3 text-[13px] leading-relaxed text-slate-400">
            Manage workspaces in the main panel. Each workspace has its own root
            folder, command policy, and private chats.
          </p>
        ) : (
          <>
            {visible.length === 0 && (
              <p className="p-3 text-[13px] leading-relaxed text-slate-400">
                {hasOtherWsThreads
                  ? 'No conversations in this workspace yet. Send a message to start one.'
                  : showArchived
                    ? 'No archived conversations.'
                    : 'No conversations yet. Send a message to start one.'}
              </p>
            )}
            {visible.map((thread) => (
              <div
                key={thread.thread_id}
                className={`group mb-0.5 flex items-center gap-1 rounded-lg ${
                  activeId === thread.thread_id ? 'bg-indigo-500/20' : ''
                }`}
              >
                <button
                  className="flex min-w-0 flex-1 cursor-pointer flex-col gap-1 rounded-lg p-2.5 text-left text-sm hover:bg-white/5 disabled:cursor-wait"
                  onClick={() => onSelect(thread.thread_id)}
                  disabled={disabled}
                  title={thread.thread_id}
                >
                  <span className="truncate text-slate-100">{threadLabel(thread)}</span>
                  <span className="truncate text-xs text-slate-400">
                    {thread.message_count} messages · {formatTimestamp(thread.updated_at)}
                  </span>
                </button>
                <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    className="cursor-pointer rounded-md p-1.5 text-slate-400 hover:bg-white/5 hover:text-white"
                    onClick={() => onRename(thread.thread_id)}
                    title="Rename conversation"
                    aria-label="Rename conversation"
                  >
                    <PenIcon className="h-3.5 w-3.5" />
                  </button>
                  <button
                    className="cursor-pointer rounded-md p-1.5 text-slate-400 hover:bg-white/5 hover:text-white"
                    onClick={() => onArchive(thread.thread_id)}
                    title={showArchived ? 'Unarchive conversation' : 'Archive conversation'}
                    aria-label={showArchived ? 'Unarchive conversation' : 'Archive conversation'}
                  >
                    <ArchiveIcon className="h-3.5 w-3.5" />
                  </button>
                  <button
                    className="cursor-pointer rounded-md px-1.5 py-1 text-base leading-none text-slate-400 hover:bg-white/5 hover:text-red-400 disabled:cursor-wait"
                    onClick={() => onDelete(thread.thread_id)}
                    disabled={disabled}
                    title="Delete this thread"
                    aria-label="Delete thread"
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </nav>
    </aside>
  )
}