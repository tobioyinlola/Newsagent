// Back-office session token. Same in-house sign-in as the customer app (email + password, then an emailed code for
// operators), but kept apart on purpose: its own storage key, and sessionStorage, so it never outlives the tab and the
// customer app never touches it. (The back office is served from the same site as the customer app, under /admin.)
const KEY = "newsagent.admin.token";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the session lasts until reload */
  }
}

export function signOut() {
  setToken(null);
}
