import { useState } from 'react'
import { formatTimestamp } from '../api'
import type { Workspace, WorkspaceConfig } from '../types'
import FolderPicker from './FolderPicker'

interface WorkspacesViewProps {
  workspaces: Workspace[]
  streaming: boolean
  onCreate: (name: string, rootPath: string) => Promise<void>
  onActivate: (workspaceId: string) => Promise<void>
  onUpdate: (workspaceId: string, name: string, config: WorkspaceConfig) => Promise<void>
  onDelete: (workspaceId: string) => Promise<void>
}

function lines(list: string[] | undefined): string {
  return (list ?? []).join('\n')
}

function toList(text: string): string[] {
  return text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
}

function ConfigEditor({
  initial,
  onSave,
  onCancel,
}: {
  initial: WorkspaceConfig
  onSave: (config: WorkspaceConfig) => void
  onCancel: () => void
}) {
  const [safe, setSafe] = useState(lines(initial.safe_commands))
  const [unsafe, setUnsafe] = useState(lines(initial.unsafe_commands))
  const [allowed, setAllowed] = useState(lines(initial.allowed_commands))

  return (
    <div className="mt-3 grid grid-cols-3 gap-3">
      {(
        [
          ['Safe commands (run freely)', safe, setSafe],
          ['Unsafe markers (require approval)', unsafe, setUnsafe],
          ['Allowed commands (never prompt)', allowed, setAllowed],
        ] as const
      ).map(([label, value, setter]) => (
        <div key={label}>
          <label className="mb-1 block text-xs font-medium text-slate-400">{label}</label>
          <textarea
            className="h-36 w-full resize-y rounded-md border border-white/10 bg-black/30 p-2 text-xs text-slate-200 outline-none focus:border-indigo-500"
            value={value}
            onChange={(e) => setter(e.target.value)}
            spellCheck={false}
          />
        </div>
      ))}
      <div className="col-span-3 flex justify-end gap-2">
        <button
          className="cursor-pointer rounded-md px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/5"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          className="cursor-pointer rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600"
          onClick={() =>
            onSave({
              safe_commands: toList(safe),
              unsafe_commands: toList(unsafe),
              allowed_commands: toList(allowed),
            })
          }
        >
          Save config
        </button>
      </div>
    </div>
  )
}

export default function WorkspacesView({
  workspaces,
  streaming,
  onCreate,
  onActivate,
  onUpdate,
  onDelete,
}: WorkspacesViewProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [newRoot, setNewRoot] = useState('')
  const [creating, setCreating] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)

  return (
    <main className="sidebar-scroll flex-1 overflow-y-auto bg-[#171a21] p-6 text-slate-200">
      <div className="mx-auto max-w-3xl">
        <h2 className="mb-1 text-lg font-semibold text-white">Workspaces</h2>
        <p className="mb-5 text-sm text-slate-400">
          Each workspace scopes the agent's file access to a directory root and stores its own
          command policy in a local <code>.local_agent_workspace</code> file.
        </p>

        <div className="mb-6 rounded-lg border border-white/10 bg-[#1c202b] p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">New workspace</h3>
          <div className="flex flex-col gap-2">
            <input
              className="rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-500"
              placeholder="Name, e.g. Website project"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <div className="flex gap-2">
              <input
                className="min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-500"
                placeholder="Root path, e.g. C:\sites\my-project"
                value={newRoot}
                onChange={(e) => setNewRoot(e.target.value)}
              />
              <button
                className="shrink-0 cursor-pointer rounded-md bg-white/5 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-white/10"
                onClick={() => setPickerOpen(true)}
                title="Browse to choose a folder"
              >
                Browse…
              </button>
            </div>
            <div>
              <button
                className="cursor-pointer rounded-md bg-indigo-500 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={creating || !newName.trim() || !newRoot.trim()}
                onClick={() => {
                  setCreating(true)
                  void onCreate(newName.trim(), newRoot.trim()).finally(() => {
                    setCreating(false)
                    setNewName('')
                    setNewRoot('')
                  })
                }}
              >
                {creating ? 'Creating…' : 'Create workspace'}
              </button>
            </div>
          </div>
        </div>

        <ul className="space-y-4">
          {workspaces.map((ws) => (
            <li key={ws.id} className="rounded-lg border border-white/10 bg-[#1c202b] p-4">
              <div className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="truncate text-sm font-semibold text-white">{ws.name}</h3>
                    {ws.is_default && (
                      <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300">
                        Default
                      </span>
                    )}
                    {ws.active && (
                      <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
                        Active
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-slate-400">{ws.root_path}</p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    Updated {formatTimestamp(ws.updated_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {!ws.is_default &&
                    (ws.active ? (
                      <span className="text-xs text-slate-500">Active now</span>
                    ) : (
                      <button
                        className="cursor-pointer rounded-md bg-emerald-600/25 px-2.5 py-1.5 text-xs font-medium text-emerald-200 hover:bg-emerald-600/40 disabled:cursor-not-allowed disabled:opacity-60"
                        disabled={streaming}
                        onClick={() => void onActivate(ws.id)}
                      >
                        Activate
                      </button>
                    ))}
                  <button
                    className="cursor-pointer rounded-md bg-white/5 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10"
                    onClick={() => setEditingId(editingId === ws.id ? null : ws.id)}
                  >
                    {editingId === ws.id ? 'Close config' : 'Config'}
                  </button>
                  {!ws.is_default && (
                    <button
                      className="cursor-pointer rounded-md bg-red-500/15 px-2.5 py-1.5 text-xs font-medium text-red-300 hover:bg-red-500/30"
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete workspace "${ws.name}" (${ws.root_path})?\n\n` +
                              'The workspace entry and its local .local_agent_workspace policy are removed, and any threads ' +
                              'belonging to it stop showing. Files on disk are NOT deleted. If this is the active workspace, ' +
                              'the app switches back to the default workspace.',
                          )
                        ) {
                          void onDelete(ws.id)
                        }
                      }}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
              {editingId === ws.id && (
                <ConfigEditor
                  initial={ws.config}
                  onSave={(config) => {
                    void onUpdate(ws.id, ws.name, config)
                    setEditingId(null)
                  }}
                  onCancel={() => setEditingId(null)}
                />
              )}
            </li>
          ))}
        </ul>

        <FolderPicker
          open={pickerOpen}
          onPick={(path) => {
            setNewRoot(path)
            setPickerOpen(false)
          }}
          onClose={() => setPickerOpen(false)}
        />
      </div>
    </main>
  )
}