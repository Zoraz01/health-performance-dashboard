import { SignIn } from '@clerk/react'
import { useTheme } from '../ThemeContext'

const DARK = {
  variables: {
    colorPrimary:                 '#e09a5e',
    colorBackground:              '#0d1f26',
    colorInputBackground:         '#162d36',
    colorText:                    '#f0f4f8',
    colorTextSecondary:           '#94a3b8',
    colorNeutral:                 '#4a6a76',
    colorDanger:                  '#f87171',
    colorTextOnPrimaryBackground: '#1c0f06',
    borderRadius:                 '0.75rem',
  },
  elements: {
    card: {
      backgroundColor: '#0d1f26',
      boxShadow: '0 0 0 1px rgba(148,163,184,0.14), 0 24px 48px -12px rgba(0,0,0,0.6)',
    },
    headerTitle:    { color: '#f0f4f8', fontWeight: '600' },
    headerSubtitle: { color: '#94a3b8' },
    socialButtonsBlockButton: {
      backgroundColor: '#162d36',
      border: '1px solid rgba(148,163,184,0.15)',
      color: '#f0f4f8',
    },
    socialButtonsBlockButtonText: { color: '#f0f4f8' },
    dividerLine: { backgroundColor: 'rgba(148,163,184,0.15)' },
    dividerText: { color: '#64748b' },
    formFieldLabel:     { color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.1em' },
    formFieldInput: {
      backgroundColor: '#162d36',
      border: '1px solid rgba(148,163,184,0.18)',
      color: '#f0f4f8',
    },
    formFieldInputShowPasswordButton: { color: '#94a3b8' },
    formButtonPrimary: {
      backgroundColor: '#e09a5e',
      color: '#1c0f06',
      fontWeight: '600',
    },
    footerActionText: { color: '#64748b' },
    footerActionLink: { color: '#e09a5e' },
    identityPreviewText:       { color: '#f0f4f8' },
    identityPreviewEditButton: { color: '#e09a5e' },
    badge: {
      backgroundColor: '#162d36',
      color: '#64748b',
      border: '1px solid rgba(148,163,184,0.1)',
    },
    footer: { backgroundColor: 'transparent' },
    internal: { color: '#64748b' },
  },
}

const LIGHT = {
  variables: {
    colorPrimary:                 '#b8662e',
    colorBackground:              '#ffffff',
    colorInputBackground:         '#f8fafc',
    colorText:                    '#0f172a',
    colorTextSecondary:           '#64748b',
    colorNeutral:                 '#94a3b8',
    colorDanger:                  '#dc2626',
    colorTextOnPrimaryBackground: '#ffffff',
    borderRadius:                 '0.75rem',
  },
  elements: {
    card: {
      backgroundColor: '#ffffff',
      boxShadow: '0 0 0 1px rgba(15,23,42,0.08), 0 8px 24px -4px rgba(15,23,42,0.12)',
    },
    formButtonPrimary: {
      backgroundColor: '#b8662e',
      color: '#ffffff',
      fontWeight: '600',
    },
    footerActionLink: { color: '#b8662e' },
  },
}

export default function LoginPage() {
  const { isDark } = useTheme()

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: `rgb(var(--s-950))` }}
    >
      <SignIn appearance={isDark ? DARK : LIGHT} />
    </div>
  )
}
