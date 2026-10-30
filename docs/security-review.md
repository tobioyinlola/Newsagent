# Security and privacy review (Phase 3)

**Status: engineering review complete; NOT closed.** Three things stop this being a signed-off review: (1) the legal
items in section 8 need a lawyer, (2) nobody has pen-tested a deployed environment, and (3) the deployed
configuration (Railway networking, R2 CORS, the auth provider) does not exist yet, so it could not be reviewed.
Everything below says which of those a claim rests on.

## 1. Scope and method
| Done | How |
| --- | --- |
| Code review of auth, tokens, uploads, SSRF surface, payments webhook, moderation, deletion, logging | Read the code paths; wrote a failing test for each claim before relying on it |
| Dependency audit | `pip-audit` (Python), `pnpm audit --prod` (web, renderer) |
| Secret scan | Regex scan of the working tree and **every commit** in git history; `.env` untracked |
| Behavioural verification | 256 API tests (SQLite and Postgres), 29 renderer tests, 7 browser tests, a real-stack browser test run **under the production Content-Security-Policy with zero violations** |

| Not done | Why it matters |
| --- | --- |
| Penetration test of a deployed system | No deployment exists. Needs an external tester before real customers |
| Review of Railway / Cloudflare / DNS configuration | Not created. See checklist in section 9 |
| In-house auth | Reviewed in code and tests (`tests/test_auth_flow.py`, 31 tests); not yet pen-tested. `dev:` tokens work only when `ENVIRONMENT=local` |
| Real HeyGen / Whisper / payment provider data flows | All mocked; their data-handling terms need reading |
| Load or abuse testing of the API itself | Only the renderer was load tested |

## 2. Findings
Severity is my estimate for a pilot, not a CVSS score.

| # | Sev | Finding | Status |
| --- | --- | --- | --- |
| F1 | **Critical** | `remotion` 4.0.250 had two critical advisories (remote code execution, arbitrary file write) | **Fixed**: upgraded to 4.0.537; renders re-verified |
| F2 | High | `ws` (memory-exhaustion DoS), `extract-zip` (symlink path traversal) via the renderer | **Fixed**: cleared by the upgrade plus pnpm overrides; `pnpm audit` clean |
| F3 | Medium | `react-router` < 7.18 open-redirect and constructor-injection advisories | **Fixed**: 7.18.4; e2e green |
| F4 | Medium | Brand website import resolved the hostname, then the HTTP client resolved it again: a DNS-rebinding attacker could reach internal addresses | **Fixed**: resolve once, connect to that exact IP (Host + SNI preserved); refuses if *any* answer is non-public; tested with a rebinding resolver |
| F5 | Medium | The renderer fetched any URL it was given (SSRF into the private network if its shared secret leaked) | **Fixed**: http(s) only, cloud-metadata ranges blocked, and `RENDERER_ALLOWED_HOSTS` allow-list. **Action: set it in production** |
| F6 | Medium | Moderation approval was tied to a script *version*, so an approved script lost approval when the editor re-saved identical text (found by the browser test) | **Fixed**: keyed to a fingerprint of the content |
| F7 | Medium | Redeeming an invite for an email that already had an account crashed with a 500 | **Fixed**: clean 409 |
| F8 | Medium | A mis-set environment could start the API in production with mocks, dev auth, default storage keys or no malware scanner | **Fixed**: the API refuses to start and lists every problem (`runtime_checks.py`, 20 checks, tested) |
| F9 | Low | Magic-link and share tokens appeared in access logs (and a first version leaked them through httpx's URL object) | **Fixed**: scrubbed from all log handlers and Sentry events; regression-tested including the httpx case |
| F10 | Low | No CSP or security headers | **Fixed**: CSP, nosniff, frame deny, no-referrer, COOP, Permissions-Policy (camera/mic only for the founder page), HSTS, `Cache-Control: no-store` on API responses |
| F11 | Low | `extract-zip`/Remotion downloads a headless browser at build time from a third-party host | **Accepted**: pre-fetched in the Docker build (`remotion browser ensure`), not at runtime |
| F12 | **Medium** | Rate limiter **fails open** if Redis is down | **Accepted, with caveat**: chosen so a Redis blip doesn't take the product down. Alert on `rate limiter backend unavailable` logs. Revisit before opening signup |
| F13 | Medium | Reminder emails need the raw magic link, but the spec says tokens are stored hashed | **Mitigated**: hash for lookup **plus** a Fernet-encrypted copy, deleted on submit/revoke/expiry. Residual risk: anyone with both the database and `SECRET_KEY` can read live links. Rotation of `SECRET_KEY` currently invalidates stored copies (reminders stop; links still work) |
| F14 | Medium | Moderation rules are keyword/regex starter rules written by an engineer | **Open**: a policy owner must review `services/moderation.py` and decide the LLM layer's role. English only |
| F15 | Low | Operator authorization is "email in `OPERATOR_EMAILS` and has a user row": no second factor of its own | **Fixed**: operators confirm every sign-in with an emailed code before `/v1/admin` opens, have 8 h sessions, and sign-ins are audited |
| F16 | Low | Founder takes could contain a minor's image/voice; nothing checks age | **Open (legal)**: see section 8 |
| F17 | Low | Webhook signature has no timestamp tolerance (replays are harmless because processing is idempotent) | **Accepted** |
| F18 | Info | Dependency scanners found **no** vulnerable Python packages; secret scan found nothing in the tree or history | |

## 3. Tokens, links and signed URLs
| Credential | Entropy / form | Stored | Lifetime | Revocation | Brute-force defence |
| --- | --- | --- | --- | --- | --- |
| Founder magic link | 256-bit random (`token_urlsafe(32)`) | SHA-256 hash for lookup; encrypted copy until submit/revoke/expiry | 14 days (config) | Owner revokes, a new link replaces the old, merging revokes, founder erasure revokes | 1500/10 min per token, 3000/10 min per IP; unknown, expired and revoked tokens return the **same** 404 body |
| Share link | 256-bit | SHA-256 hash only (shown once) | until revoked | Owner revoke; operator can disable sharing per workspace; deleting the project | 60/10 min |
| Invite code | 192-bit | plain (operator-issued, single use) | 14 days | expiry/use | 10/10 min; must match the invited email |
| Presigned downloads | provider-signed | n/a | 900 s (downloads), 3600 s (founder playback/clips) | expiry | n/a |
| Presigned uploads | provider-signed, key fixed server-side | n/a | 600 s (logos), 3600 s (founder chunks), 300 s (speed test) | expiry | size and type re-checked **after** upload |
| Renderer shared secret | operator-set | env | until rotated | rotate | constant-time compare; renderer on private network only |
| Payment webhook | HMAC-SHA256 over the raw body | secret in env | n/a | rotate | constant-time compare; idempotent by ledger ref |

Properties verified by tests: a token for one project cannot read or write another's take (404); chunk, photo and
speed-test keys are scoped to the token's own project; the speed-test cleanup cannot delete other files; raw tokens
never appear in the database, logs, Sentry events, the data export, or API responses other than at creation.

**Browser exposure.** The magic link is in the founder's URL bar. Mitigations: `Referrer-Policy: no-referrer` (header
and meta), `noindex`, short-lived signed URLs, and the link stops working once the interview is merged. We deliberately
do **not** strip the token from the address bar, because reloads on flaky mobile networks must keep working.

## 4. Authentication and authorization
- Every `/v1` route except health, public share, billing webhook and the founder routes requires a live session
  token (`nas_...`, stored only as a SHA-256 hash, revocable, idle and absolute expiry). Sessions end after **1 hour idle**
  (30 days absolute; operators 8 h). Sign-in is email + password (scrypt, salted; policy: 10+ chars, no email or common
  passwords). Sign-up and forgot-password use an emailed one-time code (HMAC-hashed, single use, 10 min, burned after 5 wrong
  tries); wrong password, unknown email and passwordless account all return the same 401. Changing or resetting a password
  revokes other sessions. Operators also confirm each sign-in with an emailed code. The token is kept in localStorage (no cookies, so no CSRF); XSS is the risk, which the CSP addresses.
- **Tenant isolation** is enforced per route by workspace id. Tests cover: projects, scripts, downloads, captions,
  costs, share, interview, brand assets, usage, ledger, moderation status, export, deletion, manual credits. Operators
  are separate (`/v1/admin/*`, 403 for owners, 401 without a token).
- Customers never see vendor costs: ledger responses omit `vendor_cost`; only the operator cost report has it.
- Signup is invite-only; there is no self-serve path. Local `dev:` tokens and the dev storage/pay routes exist only when
  `ENVIRONMENT=local` and are refused otherwise.
- **CSRF**: not applicable. The API authenticates with a bearer header, never cookies. CORS allows only `APP_BASE_URL`.
- Operator actions that change state are written to an append-only audit log (who, what, target, IP, details). Reads
  are not logged.

## 5. Uploads, SSRF and content
- Logos, brand guides, product images, founder photos: declared type/size checked up front; the stored object is
  **re-read** and its real size, magic bytes and active content (SVG scripts/handlers/external refs, PDF JavaScript)
  checked, then malware-scanned (ClamAV INSTREAM). A scanner outage leaves the file *pending*, never *clean*. Production
  refuses to start without `CLAMD_HOST`.
- Founder video chunks: per-chunk and per-take size caps, unlimited retakes with per-token/IP request throttling, 80 chunks maximum, processed by
  ffmpeg in the renderer (a media parser is attack surface: keep ffmpeg patched, run the renderer unprivileged with CPU
  and memory limits).
- **Not covered**: founder video/audio is not malware-scanned (media bytes are decoded, not executed; ffmpeg is the risk).
- SSRF: brand import (F4) and renderer fetches (F5).
- **Moderation** (section F14): rules + optional LLM; blocked content is refused, borderline content is held for a human
  before any paid step, and **what a founder says** is screened before the final render because it is published too.

## 6. Rate limits
| Surface | Limit | Backend |
| --- | --- | --- |
| Password sign-in | 10 / 10 min | per email, and 40 per IP (a victim can be locked out for 10 min; accepted) |
| Code requests (sign-up, forgot, operator resend) | 5 / hour | per email or invite, plus per IP |
| Code verify (sign-up, reset, operator) | 10 / 10 min | per email, invite or session, plus per IP |
| Project creation | 20 / hour | per user and IP |
| Script generation | 15 / hour | per user and IP |
| Brand import / uploads | 10 / hour, 30 / hour | per user and IP |
| Magic-link creation, retake requests | 20 / hour, 30 / hour | per user and IP |
| Share create / public share view | 20 / hour, 60 / 10 min | per user / IP |
| Checkout, account export, account delete | 10 / hour, 5 / day, 3 / day | per user and IP |
| Founder endpoints | 1500 / 10 min per token, 3000 / 10 min per IP | per token and IP |
| Paid work | per-workspace credits, spend cap, videos/day, video length; per-vendor monthly budget; operator pause switch | database |

Memory limiter locally, Redis in staging/production (F12). Per-IP limits need `TRUST_PROXY_HEADERS=true` behind Railway.

## 7. Data inventory, retention and deletion
| Data | Where | Why | Retention / deletion |
| --- | --- | --- | --- |
| Account email, workspace name | Postgres | sign-in, billing | until the workspace is deleted |
| Brief, scripts, brand kit, brand files | Postgres, R2 | produce the video | until the project/workspace is deleted |
| Finished videos, captions, thumbnails | R2 | the product | until the project is deleted |
| Founder name, title, email | Postgres | the interview, reminders | with the project |
| **Founder raw recordings** (chunks) | R2 | processing, retakes | **90 days after the video is finished**, unless the owner keeps them (daily job); on project/workspace delete; on founder request |
| Founder processed answers, transcripts, photo | R2, Postgres | the final video | with the project; on founder request |
| Consent timestamp + text version | Postgres | evidence of consent | with the project |
| Credit ledger, checkouts | Postgres | accounting | **kept after workspace deletion** (anonymised: workspace renamed `deleted-xxxx`, users removed) as financial records |
| Audit log | Postgres | accountability | kept; contains operator emails and workspace ids, never content |
| Moderation cases (content excerpt) | Postgres | review | deleted with the project/workspace |
| Logs / Sentry | Railway, Sentry | operations | tokens scrubbed; `send_default_pii=false`. **Confirm provider retention** |

Data-subject rights implemented: **export** (`GET /v1/account/export`, owner), **workspace deletion**
(`DELETE /v1/account`, typed confirmation, blocked while a video is rendering), **founder self-erasure**
(`DELETE /v1/interview/<token>/data`, owner is told, and warned that a published video may still show them),
**project deletion**. Tested end to end, including that files are gone from storage.

**Gaps**: backups still contain deleted data until they age out (needs a stated backup retention, proposed 30 days);
there is no process yet for a founder whose link has already expired or been merged (they must contact the owner);
R2 object versioning, if enabled, would keep deleted files: keep it **off** for media buckets or add a lifecycle rule.

## 8. Legal items for a lawyer (I am not giving legal advice)
The product's job is to put a person's face and voice into a video on a company's behalf. Please have counsel confirm
the following for each market you will serve. The column on the right says what the product already supports.

| Question for counsel | Frameworks to check | Product support today |
| --- | --- | --- |
| Who is controller and who is processor (you vs. each startup customer)? Founder footage is collected on the customer's behalf but processed by you | GDPR / UK GDPR; Nigeria NDPA 2023; Kenya DPA 2019; Ghana DPA 2012; South Africa POPIA | Consent text, owner/founder separation, DPA-ready data inventory above |
| Lawful basis for founder footage, and is the consent screen sufficient (specific, informed, withdrawable)? | all | Versioned consent text + timestamp stored; erasure button on the founder page |
| Is a face/voice video "biometric" or "sensitive" data in any market? (We do not extract templates or identify anyone.) | GDPR Art. 9; Illinois BIPA and other US state laws; Kenya/NG sensitive data | No identification, no cloning; video used only in its project |
| Minors: could a founder or someone in frame be under 18? Do we need an age gate or guardian consent? | all | None. **Open (F16)** |
| Registration/notification as a data controller or processor; DPO / Information Officer appointment | NDPC (Nigeria), ODPC (Kenya), Ghana DPC, POPIA Information Officer | None; org-level, not product |
| Cross-border transfers: data goes to HeyGen, Anthropic, the transcription vendor, Resend, Railway, Cloudflare, Sentry, the auth provider | transfer mechanisms (SCCs/adequacy/consent) per market | Subprocessor list below. No data-residency controls: `Workspace.region` is stored but unused |
| Data-processing agreements and security terms with each subprocessor; do any train on our data by default? | GDPR Art. 28 | Not signed. Check HeyGen, Anthropic and Whisper vendor "no training" terms |
| AI-generated content disclosure and synthetic-media rules | EU AI Act transparency (Art. 50), US state deepfake/disclosure laws, platform rules | Mandatory on-screen "Featured" and "AI-generated anchor" labels, enforced by the quality gate; disclosure in every caption |
| Advertising and endorsement claims; financial/health promotion rules | local ad regulators | Claims check requires owner confirmation; moderation holds financial/health/political/endorsement language |
| Privacy policy, terms of service, cookie/local-storage notice, breach-notification procedure and timelines (e.g. 72 hours) | all | **None written.** Runbook has a breach checklist. The consent screen links to nothing yet |
| US state privacy laws (CCPA/CPRA and others): applicability thresholds, notice at collection, sale/share, sensitive data | per state | Export + delete exist |
| Retention: is 90 days after completion defensible? Can the ledger be kept after deletion? | all; tax law | Configurable (`RAW_TAKE_RETENTION_DAYS`) |
| Records of processing / DPIA | GDPR Art. 30, 35 | Section 7 is a starting point; a DPIA is probably warranted (face/voice, AI, children risk) |

**Subprocessors (planned)**: HeyGen (avatar), Synthesia (secondary avatar), Anthropic (script + moderation),
OpenAI-compatible transcription vendor (undecided), Resend (email), Railway (hosting, Postgres, Redis), Cloudflare R2
(object storage), Sentry (errors), a payment provider (undecided).

## 9. Pre-launch checklist (infrastructure; none of this could be verified here)
- [ ] `ENVIRONMENT=production`; the API starts (the config check passes) and `USE_MOCKS=false`
- [ ] Renderer and Redis have **no public domain**; renderer reachable only over Railway private networking; `RENDERER_ALLOWED_HOSTS` set to the R2 host
- [ ] R2 bucket private; **CORS** allows only the web origin, methods PUT/GET, header `Content-Type`; object versioning off for media
- [ ] `SECRET_KEY`, `RENDERER_SHARED_SECRET`, `BILLING_WEBHOOK_SECRET` generated and stored only as Railway variables
- [ ] ClamAV reachable and definitions updating; upload of the EICAR file is refused in staging
- [ ] `OPERATOR_EMAILS` set; every operator has set a password; email deliverability of sign-in codes checked (SPF/DKIM on the Resend domain)
- [ ] `TRUST_PROXY_HEADERS=true`; Redis reachable; alert on rate-limiter failures
- [ ] Sentry DSN set, PII off; alert on error spikes; log retention reviewed
- [ ] Web served with the generated `Caddyfile` headers; HTTPS only; `API_ORIGIN`/`STORAGE_ORIGIN` set at build
- [ ] Backups scheduled and one restore performed in staging (`scripts/restore_test.py`)
- [ ] Vendor budgets set low in staging; operator email list set; pause switch tested
- [ ] Pen test by a third party against staging; fix highs before inviting customers
- [ ] Legal items in section 8 resolved; privacy policy and terms published and linked from the consent screen

## Back office separation and live interview (added)
- Admin UI moved to its own origin; API blocks `/v1/admin*` from the customer origin (`tests/test_backoffice.py`). Dev tokens
  (`dev:<email>`) still only exist when `ENVIRONMENT=local`; `ADMIN_BASE_URL` is validated at startup outside local.
- New customer endpoints (`/v1/interview/{token}/voice`, live start/skip/proceed) are rate limited, owner-scoped, and
  capped; the voice endpoint spends from the `tts` vendor budget and caps text at 600 characters.
- Camera takes are video-only and size-capped; snapshots go through the same image checks as uploads.
- Residual: the TTS provider receives the interview question text (not the founder's answers).

## Presenter clips (added)
- Operator-only endpoints (`/v1/admin/presenter-clips`), rate limited, every action audited, rights attestation recorded.
- Uploaded video is verified by magic bytes, malware-scanned (fails closed) and measured by the renderer before it can be used;
  cap 150 MB; the renderer downloads it through the same allow-listed host rules as other media.

## Back-office team and permissions (added)
- Owners are the `OPERATOR_EMAILS` and always hold every permission; they can't be edited, suspended or removed from the back office.
  Everyone else is invited from **Team** with a role (Admin, Support, Finance, Content, Viewer) or a custom list of permissions.
  Twelve permissions (`app/services/rbac.py`) are enforced per endpoint on the server with `require("<permission>")`; the back
  office only hides what a person can't use. `tests/test_rbac.py` and `frontend/e2e/team.spec.ts` cover it end to end.
- Invitation: emailed one-use link (only a SHA-256 of the token is stored; 14 days), the invitee chooses a password and confirms an
  emailed code, then signs in like any operator (password + emailed code each time, short operator sessions). The link is a POST
  body, never a URL path, so it isn't written to access logs.
- No privilege escalation: you can only grant permissions you hold, can't change your own access, and can't change someone who
  holds anything you lack. Permissions are read on every request, so a change applies at once.
- Suspend or remove signs the person out of every device immediately and blocks sign-in (and password reset). Re-inviting a removed
  person reuses their account. A customer account can't be turned into a team member by an invitation.
- Every invite, change, resend, removal and join is in the audit log (`staff.*`). Team members' internal workspace is not counted as
  a customer in the back-office reports.
