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


STYLES = {"classic", "anniversary"}


def _norm_style(style: str) -> str:
    return style if style in STYLES else "anniversary"


def build_book_context(request, style: str = "anniversary") -> dict:
    """Context for the on-screen (network-served) HTML preview."""
    return {"request": request, "kennels": _kennels_with_dogs(),
            "embed": False, "style": _norm_style(style)}


def render_book_html(embed: bool = True, style: str = "anniversary") -> str:
    kennels = _kennels_with_dogs()
    if embed:
        for k in kennels:
            for d in k["dogs"]:
                d["photo1_uri"] = _photo_data_uri(d.get("photo1_path"))
                d["photo2_uri"] = _photo_data_uri(d.get("photo2_path"))
    tmpl = _env.get_template("book/book.html")
    return tmpl.render(kennels=kennels, embed=embed, style=_norm_style(style),
                       request=None)


def assemble_pdf(style: str = "anniversary") -> str:
    """Render the full book to a PDF and return its path."""
    style = _norm_style(style)
    html = render_book_html(embed=True, style=style)
    out_dir = config.DATA_DIR / "books"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"ESSFTA_Breeder_Showcase_{config.SHOW_YEAR}_{style}.pdf"

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
        page.pdf(
            path=str(pdf_path),
            format="Letter",
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        browser.close()

    Path(html_path).unlink(missing_ok=True)
    return str(pdf_path)
