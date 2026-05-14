import { useClerk } from '@clerk/react'

function FitPulseLogo({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1,8 3.5,8 5,4.5 7,11.5 9,3 11,10.5 12.5,8 15,8" />
    </svg>
  )
}

export default function AccessDenied({ message }) {
  const { signOut } = useClerk()

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center px-6">
      {/* Logo */}
      <div className="flex items-center gap-2.5 mb-12">
        <div
          className="w-7 h-7 rounded-md grid place-items-center"
          style={{ background: 'linear-gradient(135deg, #e09a5e 0%, #b8662e 100%)', boxShadow: '0 6px 18px -8px rgba(184,102,46,0.55)' }}
        >
          <FitPulseLogo className="w-3.5 h-3.5" style={{ color: '#1d1106' }} />
        </div>
        <div className="text-[13px] font-semibold text-slate-100 tracking-tight">FitPulse</div>
      </div>

      {/* Card */}
      <div className="w-full max-w-sm rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-8 text-center">
        {/* Icon */}
        <div className="mx-auto w-14 h-14 rounded-full bg-red-500/10 ring-1 ring-red-500/20 grid place-items-center mb-5">
          <svg viewBox="0 0 24 24" className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            <circle cx="12" cy="16" r="1" fill="currentColor" />
          </svg>
        </div>

        <h1 className="text-slate-100 text-lg font-semibold mb-2">Access Denied</h1>
        <p className="text-slate-400 text-[13px] leading-relaxed mb-1">
          {message || 'You don\u2019t have permission to view this page.'}
        </p>
        <p className="text-slate-600 text-[11px] font-mono uppercase tracking-wider mb-7">
          Admin access required
        </p>

        <div className="flex flex-col gap-2.5">
          <a
            href="/"
            className="block w-full py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold transition-colors"
          >
            Back to Dashboard
          </a>
          <button
            onClick={() => signOut({ redirectUrl: '/' })}
            className="w-full py-2.5 rounded-xl text-slate-500 hover:text-red-400 text-sm font-medium transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>
    </div>
  )
}
