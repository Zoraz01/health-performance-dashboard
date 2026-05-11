import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { flushSync } from 'react-dom'

const LS_KEY = 'fitpulse_theme'

const ThemeContext = createContext({ isDark: true, toggle: () => {} })

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(() => {
    try {
      const stored = localStorage.getItem(LS_KEY)
      return stored !== null ? stored === 'dark' : true
    } catch {
      return true
    }
  })

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.remove('light')
    } else {
      document.documentElement.classList.add('light')
    }
    document.body.style.background = `rgb(var(--s-950))`
    try { localStorage.setItem(LS_KEY, isDark ? 'dark' : 'light') } catch {}
  }, [isDark])

  const toggle = useCallback((buttonEl) => {
    // Compute origin from button center, fall back to viewport center
    let x = '50%'
    let y = '50%'
    if (buttonEl) {
      const r = buttonEl.getBoundingClientRect()
      x = `${Math.round(r.left + r.width / 2)}px`
      y = `${Math.round(r.top + r.height / 2)}px`
    }
    document.documentElement.style.setProperty('--theme-x', x)
    document.documentElement.style.setProperty('--theme-y', y)

    if (!document.startViewTransition) {
      setIsDark(d => !d)
      return
    }

    document.startViewTransition(() => {
      flushSync(() => setIsDark(d => !d))
    })
  }, [])

  return (
    <ThemeContext.Provider value={{ isDark, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
