import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, useUser } from '@clerk/react'
import './index.css'
import App from './App.jsx'
import { ThemeProvider } from './ThemeContext.jsx'
import LoginPage from './components/LoginPage.jsx'
import AdminShell from './admin/AdminShell.jsx'

const CLERK_PK = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!CLERK_PK) {
  throw new Error('VITE_CLERK_PUBLISHABLE_KEY is not set in frontend/.env')
}

// eslint-disable-next-line react-refresh/only-export-components
function Root() {
  const { isSignedIn, isLoaded } = useUser()
  if (!isLoaded) return null   // wait for Clerk to resolve — never flash the login page

  const isAdmin = window.location.pathname.startsWith('/admin')

  if (isAdmin) return isSignedIn ? <AdminShell /> : <LoginPage />
  return isSignedIn ? <App /> : <LoginPage />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ClerkProvider publishableKey={CLERK_PK} afterSignOutUrl="/">
      <ThemeProvider>
        <Root />
      </ThemeProvider>
    </ClerkProvider>
  </StrictMode>,
)
