import { useCallback, useEffect, useState } from 'react'
import {
  activateWorkspace,
  createWorkspace,
  deleteThread,
  deleteWorkspace,
  fetchRunsSummary,
  fetchThreads,
  fetchWorkspaces,
  updateThread,
  updateWorkspace,
} from './api'
import ChatView from './components/ChatView'
import ConfirmDialog from './components/ConfirmDialog'
import RenameDialog from './components/RenameDialog'
import RunsView from './components/RunsView'
import Sidebar from './components/Sidebar'
import Toasts from './components/Toasts'
import WorkspacesView from './components/WorkspacesView'
import { useChatSession } from './hooks/useChatSession'
import { useToasts } from './hooks/useToasts'
import type { RunSummary, ThreadSummary, Workspace, WorkspaceConfig } from './types'

export default function App() {
  const [view, setView] = useState<'chat' | 'runs' | 'workspaces'>('chat')
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null)
  const [runSummaries, setRunSummaries] = useState<RunSummary[]>([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])

  const { toasts, notify, dismiss } = useToasts()

  const viewChat = useCallback(() => setView('chat'), [])
  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await fetchThreads())
    } catch {
      /* keep previous list */
    }
  }, [])

  const refreshWorkspaces = useCallback(async () => {
    try {
      setWorkspaces(await fetchWorkspaces())
    } catch {
      /* keep previous list */
    }
  }, [])

  useEffect(() => {
    void refreshThreads()
    void refreshWorkspaces()
  }, [refreshThreads, refreshWorkspaces])

const chat = useChatSession({
    notify,
    onNavigateChat: viewChat,
    onThreadsChanged: () => void refreshThreads(),
  })
  const { activeId, newChat, reportError } = chat

const refreshRuns = useCallback(async (reset = false) => {
    try {
      const data = await fetchRunsSummary()
      setRunSummaries(data)
      setSelectedRunId((prev) =>
        reset
          ? (data[0]?.thread_id ?? null)
          : prev ?? data[0]?.thread_id ?? null,
      )
    } catch {
      /* keep previous list */
    } finally {
      setRunsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshRuns()
  }, [refreshRuns])

const handleViewChange = useCallback(
    (v: 'chat' | 'runs' | 'workspaces') => {
      setView(v)
      if (v === 'runs') void refreshRuns()
      if (v === 'workspaces') void refreshWorkspaces()
    },
    [refreshRuns, refreshWorkspaces],
  )

  const handleActivateWorkspace = useCallback(
    async (workspaceId: string) => {
      if (workspaceId === activeId && workspaces.find((w) => w.id === workspaceId)?.active) return
      try {
        await activateWorkspace(workspaceId)
        await refreshWorkspaces()
        await refreshThreads()
        await refreshRuns(true)
        newChat()
        notify('Workspace activated')
      } catch (err) {
        reportError(err instanceof Error ? err.message : 'Failed to activate workspace')
        notify('Failed to activate workspace', 'error')
      }
    },
    [activeId, workspaces, refreshWorkspaces, refreshThreads, refreshRuns, newChat, notify, reportError],
  )

  const handleCreateWorkspace = useCallback(
    async (name: string, rootPath: string) => {
      try {
        await createWorkspace(name, rootPath)
        await refreshWorkspaces()
        notify('Workspace created')
      } catch (err) {
        reportError(err instanceof Error ? err.message : 'Failed to create workspace')
        notify('Failed to create workspace', 'error')
      }
    },
    [refreshWorkspaces, notify, reportError],
  )

  const handleUpdateWorkspace = useCallback(
    async (workspaceId: string, name: string, config: WorkspaceConfig) => {
      try {
        await updateWorkspace(workspaceId, name, config)
        await refreshWorkspaces()
        notify('Workspace saved')
      } catch (err) {
        reportError(err instanceof Error ? err.message : 'Failed to update workspace')
        notify('Failed to update workspace', 'error')
      }
    },
    [refreshWorkspaces, notify, reportError],
  )

  const handleDeleteWorkspace = useCallback(
    async (workspaceId: string) => {
      try {
        await deleteWorkspace(workspaceId)
        await refreshWorkspaces()
        await refreshThreads()
        notify('Workspace deleted')
      } catch (err) {
        reportError(err instanceof Error ? err.message : 'Failed to delete workspace')
        notify('Failed to delete workspace', 'error')
      }
    },
    [refreshWorkspaces, refreshThreads, notify, reportError],
  )

  const threadLabel = useCallback(
    (threadId: string): string => {
      const t = threads.find((x) => x.thread_id === threadId)
      return t?.title ?? t?.first_user_message ?? ''
    },
    [threads],
  )

  const handleDelete = useCallback((threadId: string) => {
    setPendingDelete(threadId)
  }, [])

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return
    const threadId = pendingDelete
    try {
await deleteThread(threadId)
      if (threadId === activeId) newChat()
      await refreshThreads()
      notify('Conversation deleted')
    } catch (err) {
      reportError(err instanceof Error ? err.message : 'Failed to delete thread')
      notify('Failed to delete conversation', 'error')
    } finally {
      setPendingDelete(null)
    }
  }, [activeId, newChat, notify, pendingDelete, refreshThreads, reportError])

  const pendingThread = threads.find((t) => t.thread_id === pendingDelete)

  const handleRename = useCallback(
    (threadId: string) => {
      setRenaming({ id: threadId, title: threadLabel(threadId) })
    },
    [threadLabel],
  )

  const submitRename = useCallback(
    async (title: string) => {
      if (!renaming) return
      try {
        await updateThread(renaming.id, { title })
        await refreshThreads()
        notify('Conversation renamed')
} catch (err) {
        reportError(err instanceof Error ? err.message : 'Failed to rename thread')
        notify('Failed to rename conversation', 'error')
      } finally {
        setRenaming(null)
      }
    },
    [refreshThreads, renaming, notify, reportError],
  )

  const toggleArchive = useCallback(
    async (threadId: string) => {
      const thread = threads.find((t) => t.thread_id === threadId)
      try {
        await updateThread(threadId, { archived: !thread?.archived })
        await refreshThreads()
        notify(!thread?.archived ? 'Conversation archived' : 'Conversation restored')
} catch (err) {
        reportError(err instanceof Error ? err.message : 'Failed to update thread')
        notify('Failed to update conversation', 'error')
      }
    },
    [notify, refreshThreads, threads, reportError],
  )

  return (
    <div className="flex h-screen">
      <Toasts toasts={toasts} onDismiss={dismiss} />
<Sidebar
        threads={threads}
        activeId={chat.activeId}
        disabled={chat.streaming}
        showArchived={showArchived}
        view={view}
        runs={runSummaries}
        runsLoading={runsLoading}
        selectedRunId={selectedRunId}
        workspaces={workspaces}
        onViewChange={handleViewChange}
        onSelectRun={setSelectedRunId}
        onToggleArchived={() => setShowArchived((v) => !v)}
        onSelect={(id) => void chat.selectThread(id)}
        onNew={chat.newChat}
        onRename={handleRename}
        onArchive={(id) => void toggleArchive(id)}
        onDelete={(id) => void handleDelete(id)}
        onWorkspaceChange={(id) => void handleActivateWorkspace(id)}
      />
      {view === 'workspaces' ? (
        <WorkspacesView
          workspaces={workspaces}
          streaming={chat.streaming}
          onCreate={(name, root) => handleCreateWorkspace(name, root)}
          onActivate={(id) => handleActivateWorkspace(id)}
          onUpdate={(id, name, config) => handleUpdateWorkspace(id, name, config)}
          onDelete={(id) => handleDeleteWorkspace(id)}
        />
      ) : view === 'runs' ? (
        <RunsView summaries={runSummaries} selectedId={selectedRunId} />
      ) : (
        <ChatView
          messages={chat.messages}
          streaming={chat.streaming}
          stream={chat.streamText}
          streamStartedAt={chat.streamStartedAt}
          streamElapsedMs={chat.streamElapsedMs}
          toolActivity={chat.toolActivity}
          approvals={chat.approvals}
          approvalDecisions={chat.approvalDecisions}
          error={chat.error}
          input={chat.input}
          onInputChange={chat.setInput}
          onSend={() => void chat.handleSend()}
          onStop={chat.handleStop}
          onDecideApproval={(id, approved, allow) => void chat.handleApproval(id, approved, allow)}
        />
      )}
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete conversation?"
        body={
          <>
            This will permanently delete{' '}
            {pendingThread
              ? `“${pendingThread.title ?? pendingThread.last_message?.content ?? 'this conversation'}”`
              : 'this conversation'}{' '}
            and all of its messages. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
      <RenameDialog
        key={renaming?.id ?? 'closed'}
        open={renaming !== null}
        currentTitle={renaming?.title ?? ''}
        onSave={(title) => void submitRename(title)}
        onCancel={() => setRenaming(null)}
      />
    </div>
  )
}
