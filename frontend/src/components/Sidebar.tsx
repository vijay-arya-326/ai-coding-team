import { useState } from 'react'
import { formatTimestamp } from '../api'
import type { RunSummary, ThreadSummary, Workspace } from '../types'
import FolderPicker from './FolderPicker'
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
  selectedWorkspaceId: string | null
  onViewChange: (view: 'chat' | 'runs' | 'workspaces') => void
  onSelectRun: (threadId: string) => void
  onToggleArchived: () => void
  onSelect: (threadId: string) => void
  onNew: () => void
  onRename: (threadId: string) => void
  onArchive: (threadId: string) => void
  onDelete: (threadId: string) => void
  onWorkspaceChange: (workspaceId: string) => void
  onSelectWorkspace: (workspaceId: string) => void
  onCreateWorkspace: (name: string, rootPath: string) => Promise<void>
  onActivateWorkspace: (workspaceId: string) => Promise<void>
  onDeleteWorkspace: (workspaceId: string) => Promise<void>
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
  selectedWorkspaceId,
  onViewChange,
  onSelectRun,
  onToggleArchived,
  onSelect,
  onNew,
  onRename,
  onArchive,
  onDelete,
  onWorkspaceChange,
  onSelectWorkspace,
  onCreateWorkspace,
  onActivateWorkspace,
  onDeleteWorkspace,
}: SidebarProps) {
  const [wsNewName, setWsNewName] = useState('')
  const [wsNewRoot, setWsNewRoot] = useState('')
  const [wsCreating, setWsCreating] = useState(false)
  const [wsPickerOpen, setWsPickerOpen] = useState(false)
  const activeWsId = workspaces.find((w) => w.active)?.id ?? 'default'
  const selectedWsId =
    workspaces.find((w) => w.id === selectedWorkspaceId)?.id ??
    workspaces.find((w) => w.active)?.id ??
    workspaces.find((w) => w.is_default)?.id ??
    workspaces[0]?.id ??
    null
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
        {view !== 'workspaces' && (
          <button
            className="cursor-pointer rounded-lg bg-indigo-500 px-3 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={onNew}
            disabled={disabled}
            title="Start a new conversation"
          >
            + New chat
          </button>
        )}
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
          <div className="flex h-full flex-col gap-2">
            <div className="shrink-0 rounded-lg border border-white/10 bg-[#1c202b] p-2.5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                New workspace
              </h3>
              <input
                className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
                placeholder="Name, e.g. Website project"
                value={wsNewName}
                onChange={(e) => setWsNewName(e.target.value)}
              />
              <div className="mt-2 flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
                  placeholder="Root path"
                  value={wsNewRoot}
                  onChange={(e) => setWsNewRoot(e.target.value)}
                />
                <button
                  className="shrink-0 cursor-pointer rounded-md bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-200 hover:bg-white/10"
                  onClick={() => setWsPickerOpen(true)}
                  title="Browse to choose a folder"
                >
                  Browse…
                </button>
              </div>
              <button
                className="mt-2 w-full cursor-pointer rounded-md bg-indigo-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={wsCreating || !wsNewName.trim() || !wsNewRoot.trim()}
                onClick={() => {
                  setWsCreating(true)
                  void onCreateWorkspace(wsNewName.trim(), wsNewRoot.trim()).finally(() => {
                    setWsCreating(false)
                    setWsNewName('')
                    setWsNewRoot('')
                  })
                }}
              >
                {wsCreating ? 'Creating…' : 'Create workspace'}
              </button>
            </div>

            <div className="sidebar-scroll min-h-0 flex flex-1 flex-col gap-2 overflow-y-auto">
              {workspaces.length === 0 && (
                <p className="p-2 text-xs text-slate-500">No workspaces yet — create one above.</p>
              )}
              {workspaces.map((ws) => (
              <div
                key={ws.id}
                className={`rounded-lg border bg-[#1c202b] p-2.5 ${
                  selectedWsId === ws.id ? 'border-indigo-500/70' : 'border-white/10'
                }`}
              >
                <button
                  className="w-full cursor-pointer text-left"
                  onClick={() => onSelectWorkspace(ws.id)}
                >
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold text-white">{ws.name}</span>
                    {ws.is_default && (
                      <span className="shrink-0 rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300">
                        Default
                      </span>
                    )}
                    {ws.active && (
                      <span className="shrink-0 rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
                        Active
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-slate-400">{ws.root_path}</p>
                </button>
                <div className="mt-2 flex items-center justify-between gap-1.5 border-t border-white/5 pt-2">
                  <span className="truncate text-[11px] text-slate-500">
                    Updated {formatTimestamp(ws.updated_at)}
                  </span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {!ws.is_default &&
                      (ws.active ? (
                        <span className="text-xs text-slate-500">Active now</span>
                      ) : (
                        <button
                          className="cursor-pointer rounded-md bg-emerald-600/25 px-2.5 py-1.5 text-xs font-medium text-emerald-200 hover:bg-emerald-600/40 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={disabled}
                          onClick={() => void onActivateWorkspace(ws.id)}
                        >
                          Activate
                        </button>
                      ))}
                    {!ws.is_default && (
                      <button
                        className="cursor-pointer rounded-md bg-red-500/15 px-2.5 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/30"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Delete workspace "${ws.name}" (${ws.root_path})?\n\n` +
                                'The workspace entry is removed (its .local_agent_workspace folder is left on disk), and any threads ' +
                                'belonging to it stop showing. Files on disk are NOT deleted. If this is the active workspace, ' +
                                'the app switches back to the default workspace.',
                            )
                          ) {
                            void onDeleteWorkspace(ws.id)
                          }
                        }}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
            </div>
          </div>
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
      <FolderPicker
        open={wsPickerOpen}
        onPick={(path) => {
          setWsNewRoot(path)
          setWsPickerOpen(false)
        }}
        onClose={() => setWsPickerOpen(false)}
      />
    </aside>
  )
}