import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import LogViewer from './LogViewer'
import AccessDenied from './AccessDenied'

export default function AdminShell() {
  const [status, setStatus] = useState('loading') // 'loading' | 'ok' | 'denied' | 'error'

  useEffect(() => {
    apiFetch('/api/admin/me')
      .then(r => {
        if (r.ok)               return setStatus('ok')
        if (r.status === 403)   return setStatus('denied')
        return setStatus('error')
      })
      .catch(() => setStatus('error'))
  }, [])

  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex items-center gap-3 text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-sm font-mono">Verifying access…</span>
        </div>
      </div>
    )
  }

  if (status === 'denied') return <AccessDenied />
  if (status === 'error')  return <AccessDenied message="Could not reach the server. Check that the backend is running." />

  return <LogViewer />
}
