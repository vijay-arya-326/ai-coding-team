import { useCallback, useEffect, useRef, useState } from 'react'
import { browseFolders, createFolder } from '../api'
import type { FolderEntry } from '../types'

const START_PATH_KEY = 'folderPickerStartPath'

interface FolderPickerProps {
  open: boolean
  onPick: (path: string) => void
  onClose: () => void
}

export default function FolderPicker({ open, onPick, onClose }: FolderPickerProps) {
  const [path, setPath] = useState('')
  const [parent, setParent] = useState<string | null>(null)
  const [entries, setEntries] = useState<FolderEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [goPath, setGoPath] = useState('')
  const resumeRef = useRef(false)

  const load = useCallback(async (p: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await browseFolders(p)
      setPath(result.path)
      setParent(result.parent)
      setEntries(result.entries)
      localStorage.setItem(START_PATH_KEY, result.path)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not list folders')
      if (resumeRef.current) {
        resumeRef.current = false
        localStorage.removeItem(START_PATH_KEY)
        void load('')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    resumeRef.current = true
    const start = localStorage.getItem(START_PATH_KEY)
    void load(start || '')
    return () => {
      resumeRef.current = false
    }
  }, [open, load])

  if (!open) return null

  async function handleCreate() {
    const name = newName.trim()
    if (!name || !path || creating) return
    setCreating(true)
    setError(null)
    try {
      await createFolder(path, name)
      setNewName('')
      await load(path)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create folder')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[70vh] w-full max-w-xl flex-col rounded-lg border border-white/10 bg-[#1c202b] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h3 className="text-sm font-semibold text-white">Select folder</h3>
          <button
            className="cursor-pointer rounded-md p-1 text-slate-400 hover:bg-white/5 hover:text-white"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
          <button
            className="shrink-0 cursor-pointer rounded-md bg-white/5 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!parent}
            onClick={() => parent && void load(parent)}
          >
            Up
          </button>
          <button
            className="shrink-0 cursor-pointer rounded-md bg-white/5 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10"
            onClick={() => void load('')}
            title="Go to your user home folder"
          >
            Home
          </button>
          <div className="truncate rounded-md bg-black/30 px-3 py-1.5 text-xs text-slate-300" title={path}>
            {path || 'This PC'}
          </div>
        </div>

        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
          <input
            className="min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-indigo-500"
            placeholder="Paste a path to jump there, e.g. ~/projects or C:\sites"
            value={goPath}
            onChange={(e) => setGoPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void load(goPath.trim())
            }}
          />
          <button
            className="shrink-0 cursor-pointer rounded-md bg-white/5 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={loading || !goPath.trim()}
            onClick={() => void load(goPath.trim())}
          >
            Go
          </button>
        </div>

        <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2">
          <input
            className="min-w-0 flex-1 rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-indigo-500"
            placeholder="New folder name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleCreate()
            }}
          />
          <button
            className="shrink-0 cursor-pointer rounded-md bg-emerald-600/25 px-2.5 py-1.5 text-xs font-medium text-emerald-200 hover:bg-emerald-600/40 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={creating || !newName.trim() || !path}
            onClick={() => void handleCreate()}
          >
            {creating ? 'Creating…' : 'New Folder'}
          </button>
        </div>

        <div className="sidebar-scroll flex-1 overflow-y-auto p-2">
          {loading && (
            <p className="p-3 text-xs text-slate-400">Loading folders…</p>
          )}
          {!loading && error && <p className="p-3 text-xs text-red-400">{error}</p>}
          {!loading && !error && entries.length === 0 && (
            <p className="p-3 text-xs text-slate-400">No subfolders here.</p>
          )}
{!loading &&
                entries.map((entry) => (
                  <button
                    key={entry.path}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-slate-200 hover:bg-white/5"
                    onClick={() => void load(entry.path)}
                  >
                    {entry.path === '<drives>' ? (
                      <svg
                        className="h-4 w-4 shrink-0 text-indigo-400"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <rect x="2" y="4" width="20" height="13" rx="2" />
                        <path d="M8 21h8M12 17v4" />
                      </svg>
                    ) : (
                      <svg
                        className="h-4 w-4 shrink-0 text-amber-400"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        aria-hidden="true"
                      >
                        <path d="M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                      </svg>
                    )}
                    <span className="truncate">{entry.name}</span>
                  </button>
                ))}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-white/10 px-4 py-3">
          <button
            className="cursor-pointer rounded-md px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/5"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="cursor-pointer rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={!path}
            onClick={() => onPick(path)}
          >
            Select this folder
          </button>
        </div>
      </div>
    </div>
  )
}