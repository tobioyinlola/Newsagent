# Outreach to outlets: how to switch it on

Everything is off until `OUTREACH_AI=on` is set on `backend`. Until then a paid request sends the original one-way email, exactly as before.

## 1. A sending and receiving address
Use a subdomain you do not use for anything else, for example `mail.yourdomain.com` (so an outreach problem never affects your normal email).
- **Sending (Resend):** verify the subdomain in Resend and add the DNS records it shows (SPF, DKIM, and a DMARC record such as `v=DMARC1; p=none; rua=mailto:you@yourdomain.com`). Set `EMAIL_FROM` to e.g. `Cover Founder <outreach@mail.yourdomain.com>`.
- **Receiving:** the subdomain also needs an MX record pointing at whatever receives the mail:
  - **Resend inbound** (if enabled on your account): add the MX records Resend gives you and, in Resend, add a webhook for `email.received` that posts to
    `https://<your api domain>/v1/webhooks/inbound-email`. Copy the webhook's signing secret (it starts with `whsec_`) into `OUTREACH_INBOUND_SECRET`.
    (Check the event fields against Resend's current docs the first time; the endpoint reads `to`, `from`, `subject`, `text`, and fetches the body by `email_id` if the event has none.)
  - **Any other provider or a small forwarder** (Postmark, Mailgun, a Cloudflare Email Worker): have it POST JSON `{"to": [...], "from": "...", "subject": "...", "text": "...", "message_id": "...", "in_reply_to": "...", "headers": {...}}`
    to the same URL with the header `X-Inbound-Secret: <OUTREACH_INBOUND_SECRET>` (any long random string).
  - **A mailbox the app reads itself:** set `OUTREACH_IMAP_HOST`, `OUTREACH_IMAP_USER`, `OUTREACH_IMAP_PASSWORD` (and `OUTREACH_IMAP_FOLDER`, default INBOX). The app checks it every minute.
- Set `OUTREACH_REPLY_DOMAIN=mail.yourdomain.com`. Each conversation then gets its own reply address `outreach+<code>@mail.yourdomain.com`, so a reply always lands on the right request. The subdomain must accept mail for any `outreach+...` address.

## 2. In the back office (Outreach)
1. **Templates and settings:** set the sender name and title and the company's postal address (shown under every email, with the reply-STOP line), and edit the three templates.
2. **Contacts:** paste the contact list (outlet, contact name, contact email, optional template). Check it, then save. Saving also turns on automatic outreach for those outlets.
3. Switch `OUTREACH_AI=on`. From then on a paid request that names one of those outlets opens a conversation and sends the chosen template. Replies appear under Conversations.

## 3. Trying it safely
Do the whole thing on `staging` first with one contact that is your own mailbox. Reply to the email and confirm it appears in the conversation.

## 4. The AI agent
When an outlet replies, the agent reads the reply, works out what it needs (a question, a price, an acceptance, account details...), and writes our next email. **Settings > "What the AI agent may do":**
- **Drafts only (the default):** every reply waits in the conversation for you to edit and press *Approve and send*.
- **By step:** each kind of reply is marked *Automatic* or *Needs my approval*. By default the agent sends the routine ones itself (thanks, asking for rates or timing, sending the materials, answering a question about the story) and holds the rest.
- **Always a person, whatever you set:** accepting an offer, payment arrangements, asking for or confirming account details. The agent never pays anyone and never marks a request paid or published.
- **Also held for a person:** a draft that mentions an amount, bank details, a date or a link; a reply from a different company than the contact; an email that looks like it is instructing the agent; a reply the agent was not sure about; a conversation that has gone past the reply limit; anything over the daily cap.
- **Pause** stops the agent everywhere; **Take over** stops it in one conversation. *Ask the AI to draft* works even when paused.
- **Account details** an outlet sends are stored encrypted and shown masked. *Show the full details* is recorded in the audit log. Confirm them with the outlet another way (a number you already know) before paying; then press *I confirmed these*.
The agent uses the same writing model as the rest of the app (`LLM_PROVIDER`). In development (`USE_MOCKS=true`) a simple built-in stand-in reads obvious cues so you can try the whole flow without a model key.


## 5. Sending through a Gmail / Google Workspace mailbox (the simple route)
Instead of a separate sending domain, outreach can go out from, and replies can be read from, one real mailbox you own.
1. Make a mailbox such as `outreach@coverfounder.com` in Google Workspace (a free Gmail address also works, but looks personal and has a lower daily limit).
2. Turn on 2-step verification for it, then create an **app password** (Google Account > Security > App passwords). In Gmail settings, make sure IMAP is enabled.
3. In Google Admin (Workspace), authenticate the domain's email: SPF and DKIM ("Authenticate email"), and add a DMARC record such as `v=DMARC1; p=none; rua=mailto:you@coverfounder.com`. This matters most for staying out of spam.
4. On `backend`, set:
   - `OUTREACH_SMTP_HOST=smtp.gmail.com`, `OUTREACH_SMTP_USER=outreach@coverfounder.com`, `OUTREACH_SMTP_PASSWORD=<the app password>`
   - `OUTREACH_MAILBOX=outreach@coverfounder.com` (the From address; replies come back to `outreach+<code>@coverfounder.com`, which Gmail delivers to the same mailbox)
   - `OUTREACH_FROM_NAME=Cover Founder` (or a person's name)
   - `OUTREACH_IMAP_HOST=imap.gmail.com`, `OUTREACH_IMAP_USER=outreach@coverfounder.com`, `OUTREACH_IMAP_PASSWORD=<the same app password>`
   - `OUTREACH_AI=on` last.
   No `OUTREACH_REPLY_DOMAIN`, Resend inbound or webhook is needed on this route. Other emails (sign-in codes, receipts) keep going out through Resend as before.
5. In Back office > Outreach > Templates and settings, use **Send a test email to yourself** and check it lands in your inbox, not spam. Also try mail-tester.com.

## 6. Keeping outreach out of spam
Built in:
- **Replies wait** a few minutes (default 10, with some variation) after the outlet's message, as a person would. A person can tick "Send right away" for a single reply.
- **First emails are spread out** (default at least 3 minutes apart) and capped (default 30 a day, the rest go the next morning).
- **A daily limit on all outreach email** (default 150) so the mailbox is never over Google's limits.
- **Plain text**, from a real mailbox, with a clear sender name, a reply-STOP line and your postal address. Replies to a person's own message are always from the same mailbox.
Do this yourself:
- Start small (a handful of outlets a day) for the first one or two weeks, then raise the numbers.
- Ask a few friendly contacts to reply to the first emails: replies build the mailbox's reputation.
- Keep the long download links out of the first email if you can. Spam filters dislike long signed links; tell the outlet you will send materials when they reply.
