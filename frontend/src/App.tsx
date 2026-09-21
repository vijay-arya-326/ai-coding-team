import { useCallback, useEffect, useState } from 'react'
import { deleteThread, fetchRunsSummary, fetchThreads, updateThread } from './api'
import ChatView from './components/ChatView'
import ConfirmDialog from './components/ConfirmDialog'
import RenameDialog from './components/RenameDialog'
import RunsView from './components/RunsView'
import Sidebar from './components/Sidebar'
import Toasts from './components/Toasts'
import { useChatSession } from './hooks/useChatSession'
import { useToasts } from './hooks/useToasts'
import type { RunSummary, ThreadSummary } from './types'

export default function App() {
  const [view, setView] = useState<'chat' | 'runs'>('chat')
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null)
  const [runSummaries, setRunSummaries] = useState<RunSummary[]>([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  const { toasts, notify, dismiss } = useToasts()

  const viewChat = useCallback(() => setView('chat'), [])
  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await fetchThreads())
    } catch {
      /* keep previous list */
    }
  }, [])

  useEffect(() => {
    void refreshThreads()
  }, [refreshThreads])

const chat = useChatSession({
    notify,
    onNavigateChat: viewChat,
    onThreadsChanged: () => void refreshThreads(),
  })
  const { activeId, newChat, reportError } = chat

  const refreshRuns = useCallback(async () => {
    try {
      const data = await fetchRunsSummary()
      setRunSummaries(data)
      setSelectedRunId((prev) => prev ?? data[0]?.thread_id ?? null)
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
    (v: 'chat' | 'runs') => {
      setView(v)
      if (v === 'runs') void refreshRuns()
    },
    [refreshRuns],
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
        onViewChange={handleViewChange}
        onSelectRun={setSelectedRunId}
        onToggleArchived={() => setShowArchived((v) => !v)}
        onSelect={(id) => void chat.selectThread(id)}
        onNew={chat.newChat}
        onRename={handleRename}
        onArchive={(id) => void toggleArchive(id)}
        onDelete={(id) => void handleDelete(id)}
      />
      {view === 'runs' ? (
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
