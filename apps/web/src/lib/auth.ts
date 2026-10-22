// Session token storage. Sign-in is in-house (email code, optional authenticator code); the API issues a
// revocable `nas_` session token. It lives in localStorage, so the CSP (no inline/third-party script) is what
// protects it; see docs/security-review.md.
const KEY = "newsagent.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

export function signOut() {
  setToken(null);
}
