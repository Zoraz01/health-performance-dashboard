import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import {
  RouterProvider,
  createRouter,
  createRoute,
  createRootRoute,
  Outlet,
} from '@tanstack/react-router'
import { ClerkProvider, useUser } from '@clerk/react'
import './index.css'
import App from './App.jsx'
import { ThemeProvider } from './ThemeContext.jsx'
import LoginPage from './components/LoginPage.jsx'
import AdminShell from './admin/AdminShell.jsx'
import SettingsPage from './components/SettingsPage.jsx'

const CLERK_PK = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
if (!CLERK_PK) throw new Error('VITE_CLERK_PUBLISHABLE_KEY is not set')

const rootRoute = createRootRoute({
  component: () => <Outlet />,
})

function AuthGuard() {
  const { isSignedIn, isLoaded } = useUser()
  if (!isLoaded) return null  // never flash login page
  if (!isSignedIn) return <LoginPage />
  return <Outlet />
}

const authRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: 'auth',
  component: AuthGuard,
})

const indexRoute = createRoute({
  getParentRoute: () => authRoute,
  path: '/',
  component: App,
})

const adminRoute = createRoute({
  getParentRoute: () => authRoute,
  path: '/admin',
  component: AdminShell,
})

const settingsRoute = createRoute({
  getParentRoute: () => authRoute,
  path: '/settings',
  component: SettingsPage,
})

const routeTree = rootRoute.addChildren([
  authRoute.addChildren([
    indexRoute,
    adminRoute,
    settingsRoute,
  ]),
])

const router = createRouter({ routeTree })

function Root() {
  return <RouterProvider router={router} />
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
