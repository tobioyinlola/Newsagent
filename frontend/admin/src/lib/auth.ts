// Back-office session token. Same in-house sign-in as the customer app (email + password, then an emailed code for
// operators), but its own storage key and its own site: signing in here never signs you in there.
const KEY = "newsagent.admin.token";

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
    /* storage unavailable: the session lasts until reload */
  }
}

export function signOut() {
  setToken(null);
}
