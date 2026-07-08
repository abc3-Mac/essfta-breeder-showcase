"""
ESSFTA Breeder Showcase — FastAPI application.

Flow:
  1. Kennel owner enters email -> receives a magic link (Mailgun).
  2. Signs in -> dashboard of their kennel entries.
  3. Fills the kennel form, then adds up to 3 dogs (2 photos each).
  4. Admins (Albert / Patty) can see & edit everything and assemble the book.
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import config, db, images, mail

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("showcase")

app = FastAPI(title="ESSFTA Breeder Showcase")
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, max_age=60 * 60 * 12)

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# Expose brand + field constants to every template.
templates.env.globals.update(
    PALETTE=config.PALETTE,
    SHOW_YEAR=config.SHOW_YEAR,
    VENUES=config.VENUES,
    HEALTH_TESTS=config.HEALTH_TESTS,
    DOG_HEALTH_FIELDS=config.DOG_HEALTH_FIELDS,
    PEDIGREE_SLOTS=config.PEDIGREE_SLOTS,
    MAX_DOGS=config.MAX_DOGS_PER_KENNEL,
    MAX_MENTORS=config.MAX_MENTORS,
    MAX_PROMINENT=config.MAX_PROMINENT_KENNELS,
    MAX_OUR_DOGS=config.MAX_OUR_DOGS,
    MAX_AT_STUD=config.MAX_AT_STUD,
    MAX_PLANNED=config.MAX_PLANNED_BREEDINGS,
)


@app.on_event("startup")
def _startup():
    db.init_db()


# --- Session helpers ---------------------------------------------------------
def current_user(request: Request):
    return request.session.get("user")  # {"email":..., "is_admin":bool} or None


def require_user(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return u


def is_admin(request: Request) -> bool:
    u = current_user(request)
    return bool(u and u.get("is_admin"))


def can_edit_kennel(request: Request, kennel: dict) -> bool:
    u = current_user(request)
    if not u:
        return False
    return u.get("is_admin") or kennel["login_email"] == u["email"]


def _kennel_or_404(kennel_id: int) -> dict:
    k = db.get_kennel(kennel_id)
    if not k:
        raise HTTPException(404, "Kennel not found")
    return k


def _guard_kennel(request: Request, kennel_id: int) -> dict:
    k = _kennel_or_404(kennel_id)
    if not can_edit_kennel(request, k):
        raise HTTPException(403, "You don't have access to this kennel entry.")
    return k


# --- Auth --------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if current_user(request):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "sent": False})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    token = db.create_magic_link(email, config.MAGIC_LINK_TTL_MIN)
    link = f"{config.BASE_URL}/auth/{token}"
    mail.send_magic_link(email, link)
    return templates.TemplateResponse(
        "login.html", {"request": request, "sent": True, "email": email}
    )


@app.get("/auth/{token}")
def auth(request: Request, token: str):
    result = db.consume_magic_link(token)
    if not result:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "sent": False,
             "error": "That sign-in link has expired or was already used. "
                      "Please request a new one."},
        )
    email = result["email"]
    request.session["user"] = {
        "email": email,
        "is_admin": email in config.ADMIN_EMAILS,
    }
    if result.get("kennel_id"):
        return RedirectResponse(f"/kennel/{result['kennel_id']}", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# --- Dashboard ---------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    u = require_user(request)
    kennels = db.list_kennels_for_email(u["email"])
    for k in kennels:
        k["dog_count"] = db.count_dogs(k["id"])
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "user": u, "kennels": kennels}
    )


@app.post("/kennel/new")
def kennel_new(request: Request):
    u = require_user(request)
    k = db.create_kennel(u["email"], config.SHOW_YEAR)
    return RedirectResponse(f"/kennel/{k['id']}", status_code=302)


# --- Kennel form -------------------------------------------------------------
@app.get("/kennel/{kennel_id}", response_class=HTMLResponse)
def kennel_edit(request: Request, kennel_id: int):
    k = _guard_kennel(request, kennel_id)
    dogs = db.list_dogs(kennel_id)
    return templates.TemplateResponse(
        "kennel_form.html",
        {"request": request, "user": current_user(request), "k": k, "dogs": dogs},
    )


@app.post("/kennel/{kennel_id}")
async def kennel_save(request: Request, kennel_id: int):
    _guard_kennel(request, kennel_id)
    form = await request.form()

    def slist(prefix, n):
        return [form.get(f"{prefix}_{i}", "").strip() for i in range(n)]

    def nonempty(items):
        return [x for x in items if x]

    fields = {
        "kennel_name": form.get("kennel_name", "").strip(),
        "owner_name": form.get("owner_name", "").strip(),
        "location_address": form.get("location_address", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip(),
        "social_media": form.get("social_media", "").strip(),
        "year_started": form.get("year_started", "").strip(),
        "breeding_philosophy": form.get("breeding_philosophy", "").strip(),
        "mentors_json": nonempty(slist("mentor", config.MAX_MENTORS)),
        "prominent_json": nonempty(slist("prominent", config.MAX_PROMINENT_KENNELS)),
        "health_json": {t: (form.get(f"health_{t}") == "on") for t in config.HEALTH_TESTS},
        "venues_json": form.getlist("venues"),
        "our_dogs_json": [
            {"name": form.get(f"ourdog_name_{i}", "").strip(),
             "highlights": form.get(f"ourdog_hl_{i}", "").strip()}
            for i in range(config.MAX_OUR_DOGS)
            if form.get(f"ourdog_name_{i}", "").strip()
        ],
        "at_stud_json": [
            {"name": form.get(f"stud_name_{i}", "").strip(),
             "dob": form.get(f"stud_dob_{i}", "").strip(),
             "certs": form.get(f"stud_certs_{i}", "").strip()}
            for i in range(config.MAX_AT_STUD)
            if form.get(f"stud_name_{i}", "").strip()
        ],
        "planned_json": [
            {"sire_dam": form.get(f"planned_sd_{i}", "").strip(),
             "whelp": form.get(f"planned_whelp_{i}", "").strip()}
            for i in range(config.MAX_PLANNED_BREEDINGS)
            if form.get(f"planned_sd_{i}", "").strip()
        ],
    }
    db.update_kennel(kennel_id, fields)
    if form.get("_action") == "submit":
        db.update_kennel(kennel_id, {"status": "submitted"})
    return RedirectResponse(f"/kennel/{kennel_id}", status_code=302)


@app.post("/kennel/{kennel_id}/delete")
def kennel_delete(request: Request, kennel_id: int):
    _guard_kennel(request, kennel_id)
    for d in db.list_dogs(kennel_id):
        images.delete_photo(d.get("photo1_path"))
        images.delete_photo(d.get("photo2_path"))
    db.delete_kennel(kennel_id)
    dest = "/admin" if is_admin(request) else "/dashboard"
    return RedirectResponse(dest, status_code=302)


# --- Dog form ----------------------------------------------------------------
@app.post("/kennel/{kennel_id}/dog/new")
def dog_new(request: Request, kennel_id: int):
    _guard_kennel(request, kennel_id)
    if db.count_dogs(kennel_id) >= config.MAX_DOGS_PER_KENNEL:
        raise HTTPException(400, f"Limit is {config.MAX_DOGS_PER_KENNEL} dogs per kennel.")
    d = db.create_dog(kennel_id)
    return RedirectResponse(f"/dog/{d['id']}", status_code=302)


def _guard_dog(request: Request, dog_id: int):
    d = db.get_dog(dog_id)
    if not d:
        raise HTTPException(404, "Dog not found")
    k = _guard_kennel(request, d["kennel_id"])
    return d, k


@app.get("/dog/{dog_id}", response_class=HTMLResponse)
def dog_edit(request: Request, dog_id: int):
    d, k = _guard_dog(request, dog_id)
    return templates.TemplateResponse(
        "dog_form.html",
        {"request": request, "user": current_user(request), "d": d, "k": k},
    )


@app.post("/dog/{dog_id}")
async def dog_save(request: Request, dog_id: int):
    _guard_dog(request, dog_id)
    form = await request.form()
    fields = {
        "registered_name": form.get("registered_name", "").strip(),
        "breeders": form.get("breeders", "").strip(),
        "owner_name": form.get("owner_name", "").strip(),
        "owner_address": form.get("owner_address", "").strip(),
        "owner_email": form.get("owner_email", "").strip(),
        "owner_phone": form.get("owner_phone", "").strip(),
        "call_name": form.get("call_name", "").strip(),
        "dob": form.get("dob", "").strip(),
        "color": form.get("color", "").strip(),
        "career_highlights": form.get("career_highlights", "").strip(),
        "best_virtues": form.get("best_virtues", "").strip(),
        "wish_list": form.get("wish_list", "").strip(),
        "has_produced": form.get("has_produced", "").strip(),
        "pedigree_json": {
            key: form.get(f"ped_{key}", "").strip() for key, _ in config.PEDIGREE_SLOTS
        },
        "health_json": {
            key: form.get(f"health_{key}", "").strip() for key, _ in config.DOG_HEALTH_FIELDS
        },
    }
    db.update_dog(dog_id, fields)
    return RedirectResponse(f"/dog/{dog_id}", status_code=302)


@app.post("/dog/{dog_id}/photo/{slot}")
async def dog_photo(request: Request, dog_id: int, slot: int, photo: UploadFile = File(...)):
    d, _ = _guard_dog(request, dog_id)
    if slot not in (1, 2):
        raise HTTPException(400, "Bad photo slot")
    if photo.content_type not in config.ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "Please upload a JPEG, PNG, or WebP image.")
    raw = await photo.read()
    if len(raw) > config.MAX_PHOTO_BYTES:
        raise HTTPException(400, "That image is too large.")
    col = f"photo{slot}_path"
    images.delete_photo(d.get(col))  # replace any existing
    fname = images.save_photo(raw, d["kennel_id"], dog_id, slot)
    db.update_dog(dog_id, {col: fname})
    return RedirectResponse(f"/dog/{dog_id}", status_code=302)


@app.post("/dog/{dog_id}/photo/{slot}/delete")
def dog_photo_delete(request: Request, dog_id: int, slot: int):
    d, _ = _guard_dog(request, dog_id)
    col = f"photo{slot}_path"
    images.delete_photo(d.get(col))
    db.update_dog(dog_id, {col: ""})
    return RedirectResponse(f"/dog/{dog_id}", status_code=302)


@app.post("/dog/{dog_id}/delete")
def dog_delete(request: Request, dog_id: int):
    d, _ = _guard_dog(request, dog_id)
    kennel_id = d["kennel_id"]
    images.delete_photo(d.get("photo1_path"))
    images.delete_photo(d.get("photo2_path"))
    db.delete_dog(dog_id)
    return RedirectResponse(f"/kennel/{kennel_id}", status_code=302)


# --- Serve uploaded photos ---------------------------------------------------
@app.get("/photo/{fname}")
def serve_photo(fname: str):
    # Basic traversal guard.
    if "/" in fname or ".." in fname:
        raise HTTPException(400)
    p = config.UPLOAD_DIR / fname
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


# --- Admin -------------------------------------------------------------------
def _require_admin(request: Request):
    if not is_admin(request):
        raise HTTPException(403, "Admins only.")


@app.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request, invited: str = ""):
    _require_admin(request)
    kennels = db.list_all_kennels(order_by_name=True)
    for k in kennels:
        k["dogs"] = db.list_dogs(k["id"])
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "user": current_user(request),
         "kennels": kennels, "invited": invited},
    )


@app.post("/admin/kennel/new")
def admin_kennel_new(request: Request, login_email: str = Form(...)):
    """Admin creates an entry on behalf of a non-technical owner."""
    _require_admin(request)
    k = db.create_kennel(login_email.strip().lower(), config.SHOW_YEAR)
    return RedirectResponse(f"/kennel/{k['id']}", status_code=302)


@app.post("/admin/invite")
def admin_invite(request: Request, owner_email: str = Form(...)):
    """Email an owner a one-click sign-in link so they can add their kennel."""
    _require_admin(request)
    owner_email = owner_email.strip().lower()
    token = db.create_magic_link(owner_email, config.MAGIC_LINK_TTL_MIN)
    link = f"{config.BASE_URL}/auth/{token}"
    inviter = current_user(request)["email"]
    mail.send_invite(owner_email, link, inviter)
    return RedirectResponse(f"/admin?invited={owner_email}", status_code=302)


@app.get("/admin/book/preview", response_class=HTMLResponse)
def book_preview(request: Request, style: str = "anniversary"):
    _require_admin(request)
    from .book.render import build_book_context
    ctx = build_book_context(request, style=style)
    return templates.TemplateResponse("book/book.html", ctx)


@app.post("/admin/book/assemble")
def book_assemble(request: Request, style: str = Form("anniversary")):
    _require_admin(request)
    from .book.render import assemble_pdf, _norm_style
    style = _norm_style(style)
    pdf_path = assemble_pdf(style)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"ESSFTA_Breeder_Showcase_{config.SHOW_YEAR}_{style}.pdf",
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}
