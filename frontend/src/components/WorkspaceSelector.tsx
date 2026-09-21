import type { Workspace } from '../types'

interface WorkspaceSelectorProps {
  workspaces: Workspace[]
  activeId: string | null
  disabled: boolean
  onChange: (workspaceId: string) => void
}

export default function WorkspaceSelector({
  workspaces,
  activeId,
  disabled,
  onChange,
}: WorkspaceSelectorProps) {
  return (
    <div className="flex items-center gap-2">
      <label
        htmlFor="workspace-select"
        className="shrink-0 text-[11px] font-medium uppercase tracking-wide text-slate-400"
      >
        Workspace
      </label>
      <select
        id="workspace-select"
        className="min-w-0 flex-1 cursor-pointer rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-indigo-500 disabled:cursor-not-allowed disabled:opacity-60"
        value={activeId ?? 'default'}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        title="Switch workspace — new chats run in this workspace"
      >
        {workspaces.map((ws) => (
          <option key={ws.id} value={ws.id}>
            {ws.name}
            {ws.is_default ? ' (default)' : ''}
          </option>
        ))}
      </select>
    </div>
  )
}