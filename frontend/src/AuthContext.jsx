import { useClerk, useUser } from '@clerk/react'

export function useAuth() {
  const { user } = useUser()
  const { signOut } = useClerk()
  return {
    user: user
      ? { id: user.id, email: user.primaryEmailAddress?.emailAddress ?? '' }
      : null,
    logout: () => signOut(),
  }
}
