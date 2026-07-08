"""Mailgun delivery for magic-link login emails.

Uses the existing mg.collver.biz Mailgun domain. If no API key is configured
(local dev), the link is logged to the console instead of sent, so the flow
is still testable without email.
"""
import logging
import os
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


def _send_via_mailgun_attach(to: str, subject: str, text: str, html: str,
                             attach_path: str, attach_name: str) -> bool:
    """Send an email with a file attachment via Mailgun (multipart/form-data)."""
    import uuid
    url = f"https://api.mailgun.net/v3/{config.MAILGUN_DOMAIN}/messages"
    boundary = "----showcase" + uuid.uuid4().hex
    fields = [("from", config.MAIL_FROM), ("to", to), ("subject", subject),
              ("text", text), ("html", html)]
    body = bytearray()
    for name, val in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += val.encode() + b"\r\n"
    with open(attach_path, "rb") as fh:
        data = fh.read()
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="attachment"; '
             f'filename="{attach_name}"\r\n').encode()
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    import base64
    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", "Basic " +
                   base64.b64encode(f"api:{config.MAILGUN_API_KEY}".encode()).decode())
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status == 200


def send_entry_copy(kennel: dict, dogs: list, pdf_path: str) -> bool:
    """Email the breeder a copy of their own kennel + dog pages as a PDF."""
    # Recipients: the account they signed in with, plus their contact email.
    recips = []
    for e in (kennel.get("login_email"), kennel.get("email")):
        e = (e or "").strip()
        if e and "@" in e and e.lower() not in [r.lower() for r in recips]:
            recips.append(e)
    if not recips:
        return False
    to = ", ".join(recips)
    kname = kennel.get("kennel_name") or "your kennel"
    dog_names = ", ".join(d.get("call_name") or d.get("registered_name") or "?" for d in dogs) or "no dogs yet"
    subject = f"Your ESSFTA Breeder Showcase entry — {kname}"
    text = (
        f"Thank you for submitting your entry to the ESSFTA {config.SHOW_YEAR} "
        f"National Specialty Breeder Showcase.\n\n"
        f"Attached is a PDF proof of your pages exactly as they'll appear in the "
        f"booklet:\nKennel: {kname}\nDogs: {dog_names}\n\n"
        f"Please review it. If anything needs changing, sign back in at "
        f"{config.BASE_URL} and edit your entry, then mark it complete again to "
        f"get an updated copy.\n\nESSFTA — 100 Years — 1926–2026"
    )
    html = f"""\
<div style="font-family:Georgia,serif;max-width:540px;margin:auto;color:#26251f;line-height:1.5">
  <div style="background:#0d3b23;color:#f6f1e2;padding:18px;text-align:center;border-radius:8px 8px 0 0">
    <div style="border:2px solid #c8a53a;color:#c8a53a;border-radius:999px;display:inline-block;padding:3px 12px;font-family:Helvetica,Arial,sans-serif;font-size:11px;letter-spacing:.1em">100 YEARS &middot; 1926&ndash;2026</div>
    <h2 style="margin:10px 0 0">Thank you!</h2>
  </div>
  <div style="border:1px solid #d8d2bf;border-top:none;padding:22px;border-radius:0 0 8px 8px">
    <p>Your entry to the {config.SHOW_YEAR} National Specialty <strong>Breeder Showcase</strong> has been received.</p>
    <p>Attached is a <strong>PDF proof</strong> of your pages exactly as they&rsquo;ll appear in the booklet:</p>
    <p style="font-size:15px"><strong>{kname}</strong><br><span style="color:#6b6858">Dogs: {dog_names}</span></p>
    <p>Please review it. Need a change? Sign back in at
       <a href="{config.BASE_URL}">{config.BASE_URL.replace('https://','')}</a>,
       edit your entry, and mark it complete again for an updated copy.</p>
  </div>
</div>"""
    attach_name = os.path.basename(pdf_path)
    if not config.MAILGUN_API_KEY:
        log.warning("MAILGUN_API_KEY not set — entry-copy (dev mode) to %s (%s)", to, attach_name)
        print(f"\n[DEV] Would email entry copy to {to} with attachment {attach_name}\n")
        return True
    try:
        return _send_via_mailgun_attach(to, subject, text, html, pdf_path, attach_name)
    except Exception as exc:  # noqa: BLE001
        log.error("Mailgun entry-copy send failed: %s", exc)
        return False


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
