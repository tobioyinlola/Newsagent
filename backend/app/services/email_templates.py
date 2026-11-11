"""Branded HTML for every email we send, built from the brand guide (docs/brand.md): ink header with the green wordmark,
navy body text, a green button. Table layout and inline styles only: that is what mail apps render reliably.
Every email also carries a plain-text twin, so text-only readers and tests see the same words."""

from html import escape

INK, NAVY, GREEN, PURPLE, PAPER, MUTED = "#222222", "#191A30", "#C0FE73", "#634EA0", "#F4F4F0", "#5B5C6E"
SUPPORT_EMAIL = "coverfounder@gmail.com"  # the same address as "Contact support" on the site
HEAD = "Inter,'Helvetica Neue',Helvetica,Arial,sans-serif"  # Inter where the mail app has it, a close sans otherwise
BODY = HEAD


def _paragraphs(text: str) -> str:
    out = []
    for block in text.strip().split("\n\n"):
        out.append(
            f'<p style="margin:0 0 16px;font:16px/1.55 {BODY};color:{NAVY}">{escape(block).replace(chr(10), "<br>")}</p>'
        )
    return "".join(out)


def logo_url() -> str:
    """The secondary logo as a picture, served by the web app (mail apps don't show SVG). Its alt text reads as the name."""
    from app.config import get_settings

    return absolute(get_settings().app_base_url.rstrip("/") + "/email-logo.png")


def absolute(url: str) -> str:
    """A link mail apps can open. A site address set without "https://" (e.g. APP_BASE_URL=app.example.com) would otherwise
    become a relative link that goes nowhere when the button is clicked."""
    u = url.strip()
    if u.startswith(("http://", "https://", "mailto:")):
        return u
    return "https://" + u.lstrip("/")


def render(
    heading: str,
    body: str,
    *,
    button: tuple[str, str] | None = None,
    code: str | None = None,
    after: str = "",
    details: list[tuple[str, str]] | None = None,
    footer: str = "You are receiving this because of activity on your Cover Founder account.",
    footer_link: tuple[str, str] | None = None,
    preheader: str = "",
    pixel: str = "",
) -> tuple[str, str]:
    """(html, text). `body`/`after` are plain text with blank lines between paragraphs."""
    code_html = (
        f'<div style="margin:8px 0 20px;padding:18px;background:{PAPER};border:2px solid {INK};border-radius:2px;'
        f'text-align:center;font:700 34px/1 {HEAD};letter-spacing:8px;color:{INK}">{escape(code)}</div>'
        if code
        else ""
    )
    rows = "".join(
        f'<tr><td style="padding:9px 14px;border-bottom:1px solid #E3E3DC;font:14px/1.4 {BODY};color:{MUTED};width:42%">{escape(k)}</td>'
        f'<td style="padding:9px 14px;border-bottom:1px solid #E3E3DC;font:600 14px/1.4 {BODY};color:{NAVY};text-align:right">{escape(v)}</td></tr>'
        for k, v in (details or [])
    )
    details_html = (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:4px 0 22px;background:{PAPER};'
        f'border:2px solid {INK};border-radius:2px">{rows}</table>'
        if rows
        else ""
    )
    if button:
        button = (button[0], absolute(button[1]))
    href = escape(button[1], quote=True) if button else ""
    # A "bulletproof" button: the whole coloured cell is the link, so it works in Gmail, Apple Mail and Outlook alike.
    button_html = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 20px"><tr>'
        f'<td bgcolor="{GREEN}" style="background:{GREEN};border:2px solid {INK};border-radius:2px">'
        f'<a href="{href}" target="_blank" rel="noopener" style="display:inline-block;padding:14px 26px;color:{INK};'
        f'font:700 16px {HEAD};text-decoration:none">{escape(button[0])}</a></td></tr></table>'
        f'<p style="margin:0 0 16px;font:13px/1.5 {BODY};color:{MUTED}">Button not working? Copy this link into your browser:<br>'
        f'<a href="{href}" target="_blank" rel="noopener" style="color:{PURPLE};word-break:break-all">{escape(button[1])}</a></p>'
        if button
        else ""
    )
    footer_html = (
        f' <a href="{escape(absolute(footer_link[1]), quote=True)}" style="color:{PURPLE}">{escape(footer_link[0])}</a>'
        if footer_link
        else ""
    )
    hidden = (  # the grey line a mail app shows beside the subject; invisible in the opened email
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{escape(preheader)}</div>'
        if preheader
        else ""
    )
    pixel_html = (
        f'<img src="{escape(pixel, quote=True)}" width="1" height="1" alt="" style="display:block;border:0;width:1px;height:1px">'
        if pixel
        else ""
    )
    html = (
        f'<!doctype html><html><body style="margin:0;padding:0;background:{PAPER}">{hidden}'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:24px 12px">'
        f'<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#fff;border:2px solid {INK}">'
        f'<tr><td style="background:{INK};padding:18px 28px;font:700 18px {HEAD};color:{GREEN};letter-spacing:1px">'
        f'<img src="{escape(logo_url(), quote=True)}" width="174" height="60" alt="COVER FOUNDER" '
        f'style="display:block;border:0;width:174px;height:60px;color:{GREEN};font:700 18px {HEAD}"></td></tr>'
        f'<tr><td style="padding:32px 28px 12px"><h1 style="margin:0 0 18px;font:700 24px/1.25 {HEAD};color:{INK}">{escape(heading)}</h1>'
        f"{_paragraphs(body)}{code_html}{details_html}{button_html}{_paragraphs(after) if after else ''}</td></tr>"
        f'<tr><td style="padding:16px 28px 28px;border-top:1px solid #E3E3DC;font:12px/1.5 {BODY};color:{MUTED}">{escape(footer)}{footer_html}</td></tr>'
        f"</table></td></tr></table>{pixel_html}</body></html>"
    )
    text = f"{heading}\n\n{body.strip()}\n"
    if code:
        text += f"\n    {code}\n"
    if details:
        text += "\n" + "\n".join(f"{k}: {v}" for k, v in details) + "\n"
    if button:
        text += f"\n{button[0]}: {button[1]}\n"
    if after:
        text += f"\n{after.strip()}\n"
    text += f"\n--\n{footer}\n"
    if footer_link:
        text += f"{footer_link[0]}: {absolute(footer_link[1])}\n"
    return html, text


# ---------- the emails ----------
def sign_in_code(kind: str, code: str, minutes: int) -> tuple[str, str, str]:
    """(subject, html, text) for a one-time code. kind: signup | login | reset."""
    copy = {
        "signup": (
            "Confirm your email",
            "Welcome to Cover Founder. Enter this code to confirm your email and finish creating your account.",
        ),
        "login": ("Finish signing in", "Enter this code to finish signing in."),
        "reset": ("Reset your password", "Enter this code to choose a new password."),
        "staff": (
            "Confirm your email",
            "Enter this code to confirm your email and finish joining the Cover Founder team.",
        ),
    }[kind]
    html, text = render(
        copy[0],
        copy[1],
        code=code,
        after=f"The code works once and expires in {minutes} minutes. If you asked for more than one code, use the newest.\n\n"
        "Didn't ask for this? You can ignore this email: nobody can get in without the code. Never share it with anyone.",
        footer="Cover Founder will never ask you for this code by phone or chat.",
    )
    return f"{code} is your Cover Founder code", html, text


def _span(hours: int) -> str:
    return f"{hours // 24} days" if hours >= 72 and hours % 24 == 0 else f"{hours} hours"


def invite(workspace: str, signup_url: str, hours: int, credits: str | None = None) -> tuple[str, str, str]:
    body = (
        f"You've been invited to Cover Founder, where businesses turn a short interview into a news-style video presented by an "
        f"AI-generated anchor.\n\nYour workspace, {workspace}, is ready"
        + (f" with {credits} starting credits." if credits else ".")
    )
    after = (
        "How to sign up:\n1. Press the button above (or open the link).\n2. Check this email address matches the one you were "
        "invited on, then choose a password of at least 10 characters.\n3. We email you a 6-digit code. Enter it to confirm your email.\n"
        "4. You land on your dashboard, ready to make your first video.\n\n"
        f"The invitation can be used once and stays valid for {_span(hours)}."
    )
    html, text = render(
        "You're invited to Cover Founder", body, button=("Create your account", signup_url), after=after
    )
    return "You're invited to Cover Founder", html, text


def notice(heading: str, body: str, link: tuple[str, str] | None = None) -> tuple[str, str]:
    """A plain notification with an optional button, for project, billing and moderation updates."""
    return render(heading, body, button=link)


def staff_invite(inviter: str, role: str, join_url: str, hours: int, name: str = "") -> tuple[str, str, str]:
    body = (
        f"{name + ', ' if name else ''}{inviter} has invited you to join the Cover Founder team as {role}. "
        "You'll use the back office to look after customers and their videos.\n\n"
        "What you can do depends on your role. Your team's admins can change it at any time."
    )
    after = (
        "How to join:\n1. Press the button above (or open the link).\n2. Choose a password of at least 10 characters.\n"
        "3. We email you a 6-digit code. Enter it to confirm your email.\n4. You're in. Each time you sign in we'll email you a code.\n\n"
        f"The invitation can be used once and stays valid for {_span(hours)}. Weren't expecting it? Ignore this email: "
        "nothing happens unless you open the link."
    )
    html, text = render(
        "You're invited to the Cover Founder team", body, button=("Join the team", join_url), after=after
    )
    return "You're invited to the Cover Founder team", html, text


def payment_receipt(
    *,
    invoice_no: str,
    paid_on: str,
    billed_to: str,
    amount: str,
    credits: str,
    balance: str,
    method: str,
    reference: str,
    sign_in_url: str,
) -> tuple[str, str, str]:
    """(subject, html, text): the confirmation and invoice sent once a card payment has gone through and the credits are in."""
    body = (
        f"Thank you. You've paid {amount} for {credits} credits, and they are already in your wallet.\n\n"
        "Your invoice is below. Keep this email as your receipt."
    )
    after = (
        "Ready to make your first story? Sign in to Cover Founder to start creating your videos. "
        "Each video costs 1 credit.\n\n"
        f"Questions about this payment? Email {SUPPORT_EMAIL} and quote the invoice number."
    )
    html, text = render(
        "Payment received, thank you",
        body,
        details=[
            ("Invoice number", invoice_no),
            ("Date paid", paid_on),
            ("Billed to", billed_to),
            ("Amount paid", amount),
            ("Credits added", credits),
            ("New balance", f"{balance} credits"),
            ("Payment method", method),
            ("Payment reference", reference),
        ],
        button=("Sign in to start creating", sign_in_url),
        after=after,
        footer="You are receiving this receipt because a payment was made for your Cover Founder workspace.",
    )
    return f"Payment received: {amount} for {credits} credits (invoice {invoice_no})", html, text


def refund_notice(
    *, invoice_no: str, refunded: str, credits_removed: str, balance: str, full: bool, sign_in_url: str
) -> tuple[str, str, str]:
    """(subject, html, text): sent when a card payment has been refunded and the matching credits taken back."""
    body = (
        f"Your {'full ' if full else ''}refund of {refunded} for invoice {invoice_no} has been processed. "
        "It goes back to the card you paid with, and your bank may take a few days to show it.\n\n"
        + (
            f"{credits_removed} credits were taken off your wallet to match. Your balance is now {balance} credits."
            if credits_removed not in {"0.00", "0"}
            else f"No credits needed to be taken off your wallet. Your balance is {balance} credits."
        )
    )
    html, text = render(
        "Your refund has been processed",
        body,
        button=("View your billing", sign_in_url),
        after=f"Questions about this refund? Email {SUPPORT_EMAIL} and quote the invoice number.",
        footer="You are receiving this because a payment for your Cover Founder workspace was refunded.",
    )
    return f"Refund processed: {refunded} (invoice {invoice_no})", html, text
