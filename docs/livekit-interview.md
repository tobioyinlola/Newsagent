# LiveKit for the AI interview

**Status: built and tested up to the LiveKit server; not yet run against one.** This environment cannot reach or run a LiveKit
server, so the join tokens are checked with LiveKit's own verifier and the agent is import- and logic-tested, but a real room has
not been joined. Treat the first run against your LiveKit project as the real test.

## What it is, and what it costs

The interview already works in the browser alone (camera and microphone recorded per answer, the interviewer's voice from our TTS
provider or the browser). LiveKit is an **optional layer**:

- the founder's browser joins a LiveKit room and publishes camera and microphone into it;
- a small **interviewer agent** (`agent/interviewer.py`) is started by LiveKit when the founder joins, and **speaks the
  interview's own lines** when the page asks for them (`greeting`, `q0`…, `thanks`, `closing`).

The agent is deliberately **scripted: no language model and no speech-to-text**. A whole interview is a few text-to-speech calls,
capped at 3,000 characters per room (`agent/protocol.py`). Answers are still recorded by the page and transcribed by the main
app, exactly as before, so nothing downstream changed.

**Safe by design:** if LiveKit isn't configured, the room can't be joined, or the agent doesn't announce itself within 6 seconds,
the page carries on with the browser path. A missing agent mid-interview falls back line by line. LiveKit can never stall an
interview.

## Turning it on

1. Create a LiveKit Cloud project (or self-host). Note its `wss://` URL, API key and API secret.
2. API environment: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `LIVEKIT_AGENT_ENABLED=true` once the agent in step 4 is running (until then the interview uses the browser voice) (set them as environment secrets; never paste them in chat).
3. Web build: `LIVEKIT_ORIGIN=wss://<project>.livekit.cloud` so the Content-Security-Policy allows the connection.
4. Run the agent where it can reach LiveKit and the API: build `agent/Dockerfile`; it needs `LIVEKIT_URL`, `LIVEKIT_API_KEY`,
   `LIVEKIT_API_SECRET` and `TTS_API_KEY` (an OpenAI key; `TTS_MODEL` / `TTS_VOICE` optional). Its agent name is `cf-interviewer`
   (`LIVEKIT_AGENT_NAME` on the API must match `AGENT_NAME` on the agent).
5. `GET /v1/capabilities` now reports `"interview_room": "livekit"`.

## How a join works

`POST /v1/interview/{token}/realtime` (the interview's own token) returns `{url, token, room}`. The token is for this project's room
only, expires in an hour, and asks LiveKit to dispatch `cf-interviewer` with `{api, token}` as metadata, which is how the agent
reads `GET /v1/interview/{token}/lines`: plain text, no audio, no spend. The page and the agent talk over the data topic
`cf.interview`: the page sends `{"t":"say","key":"q0"}`; the agent answers `said` (or `refused` when the budget or the key doesn't
fit).

## Not built (on purpose, to keep it cheap)

- Follow-up questions generated live. That needs speech-to-text and a language model on every turn; it is the natural next step if
  you want a conversational interviewer, and it would be billed per turn.
- Server-side recording through LiveKit Egress. The page's per-answer recording and chunked upload is the source of truth today.
