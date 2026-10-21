// Token storage. The real provider (Clerk/Auth0) is undecided, so sign-in is behind this one module:
// swap `signIn`/`getToken` for the provider SDK and nothing else changes.
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

// Dev sign-in only exists in dev builds; the API only honours `dev:` tokens when ENVIRONMENT=local.
export const DEV_AUTH = import.meta.env.DEV || import.meta.env.VITE_AUTH_MODE === "dev";

export function devSignIn(email: string) {
  setToken(`dev:${email.trim().toLowerCase()}`);
}

export function signOut() {
  setToken(null);
}
