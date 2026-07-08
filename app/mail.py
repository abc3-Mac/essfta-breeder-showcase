"""Mailgun delivery for magic-link login emails.

Uses the existing mg.collver.biz Mailgun domain. If no API key is configured
(local dev), the link is logged to the console instead of sent, so the flow
is still testable without email.
"""
import logging
import urllib.parse
import urllib.request

from . import config

log = logging.getLogger("showcase.mail")


def _send_via_mailgun(to: str, subject: str, text: str, html: str) -> bool:
    url = f"https://api.mailgun.net/v3/{config.MAILGUN_DOMAIN}/messages"
    data = urllib.parse.urlencode({
        "from": config.MAIL_FROM,
        "to": to,
        "subject": subject,
        "text": text,
        "html": html,
    }).encode()
    auth = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    auth.add_password(None, url, "api", config.MAILGUN_API_KEY)
    opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(auth))
    req = urllib.request.Request(url, data=data)
    with opener.open(req, timeout=20) as resp:
        return resp.status == 200


def send_admin_notice(kennel: dict, dogs: list) -> bool:
    """Notify all admins when a breeder marks an entry complete."""
    to = ", ".join(sorted(config.ADMIN_EMAILS))
    if not to:
        return False
    kname = kennel.get("kennel_name") or "Untitled kennel"
    owner = kennel.get("owner_name") or ""
    dog_names = ", ".join(d.get("call_name") or d.get("registered_name") or "?" for d in dogs) or "none"
    link = f"{config.BASE_URL}/kennel/{kennel['id']}"
    subject = f"Breeder Showcase entry submitted: {kname}"
    text = (
        f"A breeder marked their {config.SHOW_YEAR} Breeder Showcase entry complete.\n\n"
        f"Kennel: {kname}\nOwner: {owner}\nContact: {kennel.get('email','')} "
        f"{kennel.get('phone','')}\nDogs ({len(dogs)}): {dog_names}\n\n"
        f"Review/edit: {link}\n"
    )
    html = f"""\
<div style="font-family:Georgia,serif;max-width:520px;margin:auto;color:#26251f">
  <h2 style="color:#15532f">Entry submitted &middot; {kname}</h2>
  <p>A breeder marked their {config.SHOW_YEAR} Breeder Showcase entry complete.</p>
  <table style="font-size:14px;border-collapse:collapse">
    <tr><td style="color:#6b6858;padding:2px 10px 2px 0">Kennel</td><td>{kname}</td></tr>
    <tr><td style="color:#6b6858;padding:2px 10px 2px 0">Owner</td><td>{owner}</td></tr>
    <tr><td style="color:#6b6858;padding:2px 10px 2px 0">Contact</td><td>{kennel.get('email','')} {kennel.get('phone','')}</td></tr>
    <tr><td style="color:#6b6858;padding:2px 10px 2px 0">Dogs ({len(dogs)})</td><td>{dog_names}</td></tr>
  </table>
  <p style="margin:22px 0">
    <a href="{link}" style="background:#15532f;color:#fff;padding:11px 20px;
       border-radius:6px;text-decoration:none;font-family:Helvetica,Arial,sans-serif">
       Review / edit this entry</a>
  </p>
</div>"""
    if not config.MAILGUN_API_KEY:
        log.warning("MAILGUN_API_KEY not set — admin notice (dev mode) for %s", kname)
        print(f"\n[DEV] Admin notice: {kname} submitted -> {to}\n")
        return True
    try:
        return _send_via_mailgun(to, subject, text, html)
    except Exception as exc:  # noqa: BLE001
        log.error("Mailgun admin-notice send failed: %s", exc)
        return False


def send_invite(to: str, link: str, inviter: str = "ESSFTA") -> bool:
    subject = f"You're invited to the ESSFTA {config.SHOW_YEAR} Breeder Showcase"
    text = (
        f"{inviter} has invited you to add your kennel to the ESSFTA "
        f"{config.SHOW_YEAR} National Specialty Breeder Showcase booklet.\n\n"
        f"Click to get started (no password needed):\n{link}\n\n"
        f"You'll fill in your kennel information and up to 3 dogs, with 2 photos "
        f"each. You can save and come back anytime.\n\n"
        f"This link is good for {config.MAGIC_LINK_TTL_MIN} minutes; you can "
        f"request a fresh one at any time from the sign-in page."
    )
    html = f"""\
<div style="font-family:Georgia,serif;max-width:540px;margin:auto;color:#26251f">
  <div style="background:#0d3b23;color:#f6f1e2;padding:20px;text-align:center;border-radius:8px 8px 0 0">
    <div style="border:2px solid #c8a53a;color:#c8a53a;border-radius:999px;display:inline-block;padding:4px 14px;font-family:Helvetica,Arial,sans-serif;font-size:12px;letter-spacing:.1em">100 YEARS &middot; 1926&ndash;2026</div>
    <h2 style="margin:12px 0 0">ESSFTA Breeder Showcase</h2>
    <div style="color:#c8a53a;font-style:italic">&ldquo;Paw-cific Northwest!&rdquo;</div>
  </div>
  <div style="border:1px solid #d8d2bf;border-top:none;padding:22px;border-radius:0 0 8px 8px">
    <p>You've been invited to add your kennel to the {config.SHOW_YEAR} National
       Specialty Breeder Showcase booklet.</p>
    <p>You'll enter your kennel information and up to <strong>3 dogs</strong>
       (2 photos each). No password — just click below. You can save and return
       anytime.</p>
    <p style="margin:26px 0;text-align:center">
      <a href="{link}" style="background:#15532f;color:#fff;padding:13px 26px;
         border-radius:6px;text-decoration:none;font-family:Helvetica,Arial,sans-serif;
         font-weight:bold">Start my kennel entry</a>
    </p>
    <p style="font-size:13px;color:#666">Link valid for {config.MAGIC_LINK_TTL_MIN}
       minutes. Need a new one? Request it anytime from the sign-in page.</p>
  </div>
</div>"""
    if not config.MAILGUN_API_KEY:
        log.warning("MAILGUN_API_KEY not set — invite link (dev mode): %s", link)
        print(f"\n[DEV] Invite link for {to}:\n{link}\n")
        return True
    try:
        return _send_via_mailgun(to, subject, text, html)
    except Exception as exc:  # noqa: BLE001
        log.error("Mailgun invite send failed: %s", exc)
        return False


def send_magic_link(to: str, link: str) -> bool:
    subject = f"Your ESSFTA Breeder Showcase sign-in link"
    text = (
        f"Click to sign in to the ESSFTA {config.SHOW_YEAR} Breeder Showcase:\n\n"
        f"{link}\n\n"
        f"This link is good for {config.MAGIC_LINK_TTL_MIN} minutes and can be "
        f"used once. If you didn't request it, you can ignore this email."
    )
    html = f"""\
<div style="font-family:Georgia,serif;max-width:520px;margin:auto;color:#26251f">
  <h2 style="color:#15532f">ESSFTA Breeder Showcase</h2>
  <p>Click below to sign in and work on your kennel entry.</p>
  <p style="margin:28px 0">
    <a href="{link}" style="background:#15532f;color:#fff;padding:12px 22px;
       border-radius:6px;text-decoration:none;font-family:Helvetica,Arial,sans-serif">
       Sign in to the Showcase</a>
  </p>
  <p style="font-size:13px;color:#666">This link works for
     {config.MAGIC_LINK_TTL_MIN} minutes and can be used once.
     If you didn't request it, ignore this email.</p>
  <p style="font-size:12px;color:#999">ESSFTA · 100 Years · 1926&ndash;2026</p>
</div>"""

    if not config.MAILGUN_API_KEY:
        log.warning("MAILGUN_API_KEY not set — magic link (dev mode): %s", link)
        print(f"\n[DEV] Magic link for {to}:\n{link}\n")
        return True
    try:
        return _send_via_mailgun(to, subject, text, html)
    except Exception as exc:  # noqa: BLE001
        log.error("Mailgun send failed: %s", exc)
        return False
