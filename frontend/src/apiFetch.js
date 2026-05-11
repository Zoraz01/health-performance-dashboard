/**
 * Thin fetch wrapper that attaches a Clerk session token to every request.
 * Uses window.Clerk (set automatically by @clerk/react) so this utility
 * can be called from non-React modules without threading hooks through.
 *
 * On 401: retries once with a fresh token (handles token-refresh races)
 * before signing out.
 */

async function _getToken(skipCache = false) {
  return await window.Clerk?.session?.getToken({ skipCache }) ?? null
}

async function _buildHeaders(options, token) {
  return {
    ...(options.headers ?? {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

export default async function apiFetch(url, options = {}) {
  const token = await _getToken()
  const res = await fetch(url, { ...options, headers: await _buildHeaders(options, token) })

  if (res.status === 401) {
    // Retry once with a cache-busted fresh token before giving up
    const freshToken = await _getToken(true)
    if (freshToken && freshToken !== token) {
      const retry = await fetch(url, { ...options, headers: await _buildHeaders(options, freshToken) })
      if (retry.status !== 401) return retry
    }
    await window.Clerk?.signOut()
    return res
  }

  return res
}
