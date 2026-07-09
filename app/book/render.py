"""
Book assembly: turn every kennel + its dogs into one print-ready PDF.

Order: kennels alphabetically by name; each kennel page is immediately
followed by that kennel's dog pages (also alphabetical by call name).

For the PDF we embed photos as base64 data URIs and render from a local
file, so Playwright needs neither an admin session nor network access.
The on-screen HTML preview instead points at the live /photo/ route.
"""
import base64
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config, db

BASE = Path(__file__).resolve().parent.parent
_env = Environment(
    loader=FileSystemLoader(str(BASE / "templates")),
    autoescape=select_autoescape(["html"]),
)
_env.globals.update(
    PALETTE=config.PALETTE,
    SHOW_YEAR=config.SHOW_YEAR,
    VENUES=config.VENUES,
    HEALTH_TESTS=config.HEALTH_TESTS,
    DOG_HEALTH_FIELDS=config.DOG_HEALTH_FIELDS,
    PEDIGREE_SLOTS=config.PEDIGREE_SLOTS,
)


def _kennels_with_dogs() -> list:
    # Only kennels with a name make it into the book; blank/abandoned drafts
    # are skipped so they never produce an empty page.
    kennels = [k for k in db.list_all_kennels(order_by_name=True)
               if (k.get("kennel_name") or "").strip()]
    for k in kennels:
        dogs = db.list_dogs(k["id"])
        dogs.sort(key=lambda d: (d.get("call_name") or d.get("registered_name") or "").lower())
        k["dogs"] = dogs
    return kennels


def _photo_data_uri(fname: str) -> str:
    if not fname:
        return ""
    p = config.UPLOAD_DIR / fname
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:image/jpeg;base64,{b64}"


_FONT_CACHE = None


def font_face_css() -> str:
    """@font-face rules with the booklet fonts embedded as data URIs, so the
    PDF renders identically on any machine (local Mac and Linux container)."""
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE
    faces = []
    for family, fname in (("ESSSans", "SourceSans3.ttf"),
                          ("ESSSerif", "SourceSerif4.ttf")):
        p = BASE / "static" / "fonts" / fname
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        faces.append(
            f'@font-face{{font-family:"{family}";'
            f'src:url(data:font/ttf;base64,{b64}) format("truetype");'
            f'font-weight:200 900;font-style:normal;font-display:swap;}}'
        )
    _FONT_CACHE = "\n".join(faces)
    return _FONT_CACHE


STYLES = {"classic", "anniversary"}


def _norm_style(style: str) -> str:
    return style if style in STYLES else "anniversary"


def build_book_context(request, style: str = "anniversary") -> dict:
    """Context for the on-screen (network-served) HTML preview."""
    return {"request": request, "kennels": _kennels_with_dogs(),
            "embed": False, "style": _norm_style(style),
            "font_faces": font_face_css()}


def _embed_photos(kennels: list):
    for k in kennels:
        for d in k["dogs"]:
            d["photo1_uri"] = _photo_data_uri(d.get("photo1_path"))
            d["photo2_uri"] = _photo_data_uri(d.get("photo2_path"))


def render_book_html(embed: bool = True, style: str = "anniversary") -> str:
    kennels = _kennels_with_dogs()
    if embed:
        _embed_photos(kennels)
    tmpl = _env.get_template("book/book.html")
    return tmpl.render(kennels=kennels, embed=embed, style=_norm_style(style),
                       font_faces=font_face_css(), request=None)


def _render_pdf(html: str, pdf_path) -> str:
    """Render an HTML string to a Letter-size PDF via headless Chromium."""
    out_dir = Path(pdf_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, dir=out_dir, encoding="utf-8"
    ) as f:
        f.write(html)
        html_path = f.name
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page()
        page.goto("file://" + html_path, wait_until="load")
        # Ensure embedded fonts are loaded (and the fit-to-page script has run)
        # before capturing, so measurements use real metrics.
        try:
            page.evaluate("async () => { await document.fonts.ready; }")
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(150)
        page.pdf(
            path=str(pdf_path),
            format="Letter",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()
    Path(html_path).unlink(missing_ok=True)
    return str(pdf_path)


def assemble_pdf(style: str = "anniversary") -> str:
    """Render the full book to a PDF and return its path."""
    style = _norm_style(style)
    html = render_book_html(embed=True, style=style)
    pdf_path = config.DATA_DIR / "books" / f"ESSFTA_Breeder_Showcase_{config.SHOW_YEAR}_{style}.pdf"
    return _render_pdf(html, pdf_path)


def assemble_kennel_pdf(kennel_id: int, style: str = "anniversary") -> str:
    """Render just ONE kennel's page + its dog pages (no cover/blank) — the
    breeder's personal copy for their confirmation email."""
    style = _norm_style(style)
    k = db.get_kennel(kennel_id)
    if not k:
        raise ValueError(f"kennel {kennel_id} not found")
    dogs = db.list_dogs(kennel_id)
    dogs.sort(key=lambda d: (d.get("call_name") or d.get("registered_name") or "").lower())
    k["dogs"] = dogs
    _embed_photos([k])
    html = _env.get_template("book/book.html").render(
        kennels=[k], embed=True, style=style, proof=True,
        font_faces=font_face_css(), request=None)
    safe = "".join(c for c in (k.get("kennel_name") or f"kennel{kennel_id}")
                   if c.isalnum() or c in " -_").strip().replace(" ", "_") or f"kennel{kennel_id}"
    pdf_path = config.DATA_DIR / "proofs" / f"{safe}_{config.SHOW_YEAR}.pdf"
    return _render_pdf(html, pdf_path)
