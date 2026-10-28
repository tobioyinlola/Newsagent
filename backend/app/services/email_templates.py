"""Branded HTML for every email we send, built from the brand guide (docs/brand.md): ink header with the green wordmark,
navy body text, a green button. Table layout and inline styles only: that is what mail apps render reliably.
Every email also carries a plain-text twin, so text-only readers and tests see the same words."""

from html import escape

INK, NAVY, GREEN, PURPLE, PAPER, MUTED = "#222222", "#191A30", "#C0FE73", "#634EA0", "#F4F4F0", "#5B5C6E"
HEAD = (
    "'Courier New',Courier,monospace"  # Space Mono is not available in mail apps; monospace is the closest safe match
)
BODY = "Roboto,Helvetica,Arial,sans-serif"


def _paragraphs(text: str) -> str:
    out = []
    for block in text.strip().split("\n\n"):
        out.append(
            f'<p style="margin:0 0 16px;font:16px/1.55 {BODY};color:{NAVY}">{escape(block).replace(chr(10), "<br>")}</p>'
        )
    return "".join(out)


def render(
    heading: str,
    body: str,
    *,
    button: tuple[str, str] | None = None,
    code: str | None = None,
    after: str = "",
    footer: str = "You are receiving this because of activity on your Cover Founder account.",
) -> tuple[str, str]:
    """(html, text). `body`/`after` are plain text with blank lines between paragraphs."""
    code_html = (
        f'<div style="margin:8px 0 20px;padding:18px;background:{PAPER};border:2px solid {INK};border-radius:2px;'
        f'text-align:center;font:700 34px/1 {HEAD};letter-spacing:8px;color:{INK}">{escape(code)}</div>'
        if code
        else ""
    )
    button_html = (
        f'<p style="margin:8px 0 20px"><a href="{escape(button[1], quote=True)}" style="display:inline-block;padding:14px 26px;'
        f"background:{GREEN};color:{INK};border:2px solid {INK};border-radius:2px;font:700 16px {HEAD};"
        f'text-decoration:none">{escape(button[0])}</a></p>'
        f'<p style="margin:0 0 16px;font:13px/1.5 {BODY};color:{MUTED}">Button not working? Copy this link into your browser:<br>'
        f'<a href="{escape(button[1], quote=True)}" style="color:{PURPLE};word-break:break-all">{escape(button[1])}</a></p>'
        if button
        else ""
    )
    html = (
        f'<!doctype html><html><body style="margin:0;padding:0;background:{PAPER}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}"><tr><td align="center" style="padding:24px 12px">'
        f'<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#fff;border:2px solid {INK}">'
        f'<tr><td style="background:{INK};padding:18px 28px;font:700 18px {HEAD};color:{GREEN};letter-spacing:1px">COVER FOUNDER</td></tr>'
        f'<tr><td style="padding:32px 28px 12px"><h1 style="margin:0 0 18px;font:700 24px/1.25 {HEAD};color:{INK}">{escape(heading)}</h1>'
        f"{_paragraphs(body)}{code_html}{button_html}{_paragraphs(after) if after else ''}</td></tr>"
        f'<tr><td style="padding:16px 28px 28px;border-top:1px solid #E3E3DC;font:12px/1.5 {BODY};color:{MUTED}">{escape(footer)}<br>'
        "Cover Founder videos use an AI-generated anchor and are always labelled as such.</td></tr>"
        "</table></td></tr></table></body></html>"
    )
    text = f"{heading}\n\n{body.strip()}\n"
    if code:
        text += f"\n    {code}\n"
    if button:
        text += f"\n{button[0]}: {button[1]}\n"
    if after:
        text += f"\n{after.strip()}\n"
    text += f"\n--\n{footer}\n"
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
        f"You've been invited to Cover Founder, where startups turn a short interview into a news-style video presented by an "
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
