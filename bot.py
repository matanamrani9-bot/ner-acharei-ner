#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
נר אחרי נר — הבוט.
רץ ב-GitHub Actions פעם ביום.

  python bot.py render    מרנדר את התמונות של הפוסט שהגיע זמנו
  python bot.py publish   מפרסם אותו לאינסטגרם ומסמן בתור

התור יושב ב-queue.json. הרינדור והפרסום מופרדים כי מטא חייבת
למשוך את התמונה מכתובת ציבורית, ולכן היא צריכה להיות ב-git לפני הפרסום.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error, datetime as dt

# ---------- מיתוג. שחור על לבן, שום דבר אחר. ----------
PAPER  = (255, 255, 255)
INK    = (10, 10, 10)
FAINT  = (163, 163, 163)
GREY   = (90, 90, 90)
W, H   = 1080, 1350
MARGIN = 130
HANDLE = "@ner.acharei.ner"

FONT_URL = ("https://raw.githubusercontent.com/google/fonts/main/"
            "ofl/heebo/Heebo%5Bwght%5D.ttf")
FONT_PATH = "/tmp/Heebo.ttf"

QUEUE   = "queue.json"
TZ      = dt.timezone(dt.timedelta(hours=3))          # שעון ישראל
DISCLAIM = "התוכן כאן חינוכי בלבד ואינו ייעוץ השקעות."

GRAPH   = os.environ.get("IG_GRAPH_HOST", "https://graph.instagram.com")
VER     = os.environ.get("IG_API_VERSION", "v23.0")
TOKEN   = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER = os.environ.get("IG_USER_ID", "")
REPO    = os.environ.get("GITHUB_REPOSITORY", "")
BRANCH  = os.environ.get("GITHUB_REF_NAME", "main")
DRY     = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")


def log(*a):
    print(*a, flush=True)


def today():
    return dt.datetime.now(TZ).date()


# ---------------- התור ----------------

def load_queue():
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)


def save_queue(q):
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pick(q):
    """הפוסט הראשון שטרם פורסם ושהתאריך שלו הגיע."""
    for p in q["posts"]:
        if p.get("published_at"):
            continue
        d = dt.date.fromisoformat(p["date"])
        if d <= today():
            return p
        return None          # התור ממוין; אם הראשון עתידי, אין מה לעשות היום
    return None


# ---------------- גרפיקה ----------------

def ensure_font():
    if not os.path.exists(FONT_PATH):
        log("מוריד פונט…")
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)
    return FONT_PATH


def font(size, weight=800):
    from PIL import ImageFont
    f = ImageFont.truetype(ensure_font(), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _w(d, s, f):
    return d.textlength(s, font=f, direction="rtl", language="he")


def _wrap(d, text, f, max_w):
    out = []
    for para in text.split("\n"):
        words, cur = para.split(), ""
        for w in words:
            trial = (cur + " " + w).strip()
            if _w(d, trial, f) <= max_w or not cur:
                cur = trial
            else:
                out.append(cur); cur = w
        out.append(cur)
    return out


def _fit(d, text, max_w, max_h, hi=94, lo=44, lh=1.34):
    size = hi
    while size > lo:
        f = font(size)
        lines = _wrap(d, text, f, max_w)
        if len(lines) * size * lh <= max_h:
            return f, lines, size
        size -= 3
    f = font(lo)
    return f, _wrap(d, text, f, max_w), lo


def _handle(d):
    f = font(25, 500)
    wdt = d.textlength(HANDLE, font=f, direction="ltr")
    d.text(((W - wdt) / 2, H - 92), HANDLE, font=f, fill=FAINT, direction="ltr")


def card(text, out, counter=None, body=None):
    """כרטיס אחד. משפט במרכז, שוליים נדיבים, שקט מסביב."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    if counter:
        fc = font(24, 500)
        d.text(((W - d.textlength(counter, font=fc)) / 2, 96),
               counter, font=fc, fill=FAINT)

    max_w = W - MARGIN * 2
    f, lines, size = _fit(d, text, max_w, H * (0.34 if body else 0.46),
                          hi=86 if body else 94)
    step = int(size * 1.34)

    blines, bstep, fb = [], 0, None
    if body:
        fb = font(38, 400)
        blines = _wrap(d, body, fb, max_w)
        bstep = int(38 * 1.52)

    block = len(lines) * step + (48 + len(blines) * bstep if blines else 0)
    y = (H - block) / 2 - 24

    for ln in lines:
        d.text(((W - _w(d, ln, f)) / 2, y), ln, font=f, fill=INK,
               direction="rtl", language="he")
        y += step

    if blines:
        y += 48
        for ln in blines:
            d.text(((W - _w(d, ln, fb)) / 2, y), ln, font=fb, fill=GREY,
                   direction="rtl", language="he")
            y += bstep

    _handle(d)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, quality=96, subsampling=0)
    return out


def render_post(p):
    folder = f"posts/{p['date']}"
    files = []
    slides = p.get("slides")
    if slides:
        total = len(slides)
        for i, s in enumerate(slides, 1):
            files.append(card(s["title"], f"{folder}/{i}.jpg",
                              counter=f"{i} / {total}", body=s.get("body")))
    else:
        files.append(card(p["hook"], f"{folder}/1.jpg"))
    p["media"] = [os.path.basename(f) for f in files]
    log(f"רונדרו {len(files)} קבצים ל-{folder}")
    return files


# ---------------- אינסטגרם ----------------

def api(path, params, method="GET"):
    params = {**params, "access_token": TOKEN}
    data = urllib.parse.urlencode(params).encode()
    url = f"{GRAPH}/{VER}/{path}"
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Graph API {e.code}: {e.read().decode('utf-8','replace')}") from None


def raw_url(path):
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{urllib.parse.quote(path)}"


def caption_of(p, q):
    parts = [p.get("caption", "").strip()]
    if p.get("cta"):
        parts.append(p["cta"].strip())
    tags = p.get("hashtags") or q.get("default_hashtags", [])
    if tags:
        parts.append(" ".join("#" + t.lstrip("#") for t in tags))
    parts.append(DISCLAIM)
    return "\n\n".join(x for x in parts if x)


def publish_post(p, q):
    folder = f"posts/{p['date']}"
    media = p.get("media") or ["1.jpg"]
    cap = caption_of(p, q)

    log(f"מפרסם {p['date']} — {len(media)} קבצים")
    if DRY:
        log("DRY_RUN. הכיתוב שהיה עולה:\n" + cap)
        return None

    if len(media) > 1:
        kids = [api(f"{IG_USER}/media",
                    {"image_url": raw_url(f"{folder}/{m}"),
                     "is_carousel_item": "true"}, "POST")["id"] for m in media]
        cid = api(f"{IG_USER}/media",
                  {"media_type": "CAROUSEL", "children": ",".join(kids),
                   "caption": cap}, "POST")["id"]
    else:
        cid = api(f"{IG_USER}/media",
                  {"image_url": raw_url(f"{folder}/{media[0]}"),
                   "caption": cap}, "POST")["id"]

    mid = api(f"{IG_USER}/media_publish", {"creation_id": cid}, "POST")["id"]
    p["published_at"] = dt.datetime.now(TZ).isoformat(timespec="seconds")
    p["instagram_media_id"] = mid
    log(f"פורסם. media_id {mid}")
    return mid


# ---------------- ריצה ----------------

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "render"
    q = load_queue()
    p = pick(q)

    if not p:
        log("אין פוסט לפרסום היום.")
        return

    if mode == "render":
        render_post(p)
        save_queue(q)
    elif mode == "publish":
        if not TOKEN or not IG_USER:
            log("חסרים IG_ACCESS_TOKEN או IG_USER_ID ב-Secrets."); sys.exit(1)
        publish_post(p, q)
        save_queue(q)
    else:
        log(f"מצב לא מוכר: {mode}"); sys.exit(1)


if __name__ == "__main__":
    main()
