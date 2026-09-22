import { useState } from 'react'
import { formatTimestamp } from '../api'
import type { Workspace, WorkspaceConfig } from '../types'

interface WorkspacesViewProps {
  workspace: Workspace | null
  onUpdate: (
    workspaceId: string,
    name: string,
    config: WorkspaceConfig,
    guidelines?: string,
  ) => Promise<void>
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
  initialGuidelines,
  onSave,
}: {
  initial: WorkspaceConfig
  initialGuidelines: string
  onSave: (config: WorkspaceConfig, guidelines: string) => void
}) {
  const [safe, setSafe] = useState(lines(initial.safe_commands))
  const [unsafe, setUnsafe] = useState(lines(initial.unsafe_commands))
  const [allowed, setAllowed] = useState(lines(initial.allowed_commands))
  const [guidelines, setGuidelines] = useState(initialGuidelines)

  return (
    <div className="mt-3">
      <div className="grid grid-cols-3 gap-3">
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
              className="h-44 w-full resize-y rounded-md border border-white/10 bg-black/30 p-2 text-xs text-slate-200 outline-none focus:border-indigo-500"
              value={value}
              onChange={(e) => setter(e.target.value)}
              spellCheck={false}
            />
          </div>
        ))}
      </div>
      <div className="mt-3">
        <label className="mb-1 block text-xs font-medium text-slate-400">
          Guidelines (guidelines.md — added to the agent's system prompt here)
        </label>
        <textarea
          className="h-44 w-full resize-y rounded-md border border-white/10 bg-black/30 p-2 text-xs text-slate-200 outline-none focus:border-indigo-500"
          value={guidelines}
          onChange={(e) => setGuidelines(e.target.value)}
          spellCheck={false}
        />
      </div>
      <div className="mt-3 flex justify-end gap-2">
        <button
          className="cursor-pointer rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600"
          onClick={() =>
            onSave(
              {
                safe_commands: toList(safe),
                unsafe_commands: toList(unsafe),
                allowed_commands: toList(allowed),
              },
              guidelines,
            )
          }
        >
          Save config
        </button>
      </div>
    </div>
  )
}

export default function WorkspacesView({ workspace, onUpdate }: WorkspacesViewProps) {
  return (
    <main className="sidebar-scroll flex-1 overflow-y-auto bg-[#171a21] p-6 text-slate-200">
      <div className="mx-auto max-w-3xl">
        {workspace ? (
          <>
            <h2 className="mb-1 text-lg font-semibold text-white">{workspace.name}</h2>
            <div className="mb-3 flex items-center gap-2">
              {workspace.is_default && (
                <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-300">
                  Default
                </span>
              )}
              {workspace.active && (
                <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
                  Active
                </span>
              )}
              <span className="text-xs text-slate-400">{workspace.root_path}</span>
              <span className="ml-auto text-[11px] text-slate-500">
                Updated {formatTimestamp(workspace.updated_at)}
              </span>
            </div>
            <p className="mb-4 text-sm text-slate-400">
              Select a workspace from the left panel to view or edit here. Policy and guidelines
              are persisted to the workspace's <code>.local_agent_workspace</code> folder
              (<code>config.json</code> and <code>guidelines.md</code>).
            </p>
            <ConfigEditor
              key={workspace.id}
              initial={workspace.config}
              initialGuidelines={workspace.guidelines ?? ''}
              onSave={(config, guidelines) =>
                void onUpdate(workspace.id, workspace.name, config, guidelines)
              }
            />
          </>
        ) : (
          <p className="text-sm text-slate-500">
            No workspace selected — create one in the left panel.
          </p>
        )}
      </div>
    </main>
  )
}