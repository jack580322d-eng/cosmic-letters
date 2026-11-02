"""Render a post's two images and publish them as a carousel to Instagram and Threads.

Usage: python scripts/publish.py render  <post_id>
       python scripts/publish.py publish <post_id> [ig|threads|both]
"""
import json, os, sys, time, pathlib, urllib.request, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT = ROOT / "fonts" / "jf-openhuninn-2.1.ttf"
REPO = os.environ.get("GITHUB_REPOSITORY", "jack580322d-eng/cosmic-letters")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
FB = "https://graph.facebook.com/v25.0"
IGH = "https://graph.instagram.com/v25.0"
TH = "https://graph.threads.net/v1.0"

PAGE = """<html><head><meta charset="utf-8"><style>
@font-face{{font-family:H;src:url('{font}')}}
html,body{{margin:0;width:1080px;height:1350px;background:#000;color:#f2efe6;font-family:H}}
.wrap{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;font-size:{size}px;line-height:1.75;letter-spacing:2px}}
.gap{{height:{gap}px}}
.formula{{font-size:{fsize}px;color:#fff;margin:6px 0}}
.dim{{color:#bdb8ac}}
.foot{{position:absolute;left:0;right:0;bottom:64px;display:flex;justify-content:space-between;padding:0 72px;font-size:26px;color:#6f6b63;letter-spacing:3px}}
</style></head><body><div class="wrap">{body}</div><div class="foot"><span>{domain}</span><span>@chieh._.04</span></div></body></html>"""


def post_dir(pid):
    return ROOT / "posts" / pid


def load(pid):
    return json.loads((post_dir(pid) / "post.json").read_text(encoding="utf-8"))


def render(pid):
    from playwright.sync_api import sync_playwright
    post = load(pid)
    out = post_dir(pid)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        for name, body, size in (("img1", post["image1"], 54), ("img2", post["image2"], 42)):
            html = PAGE.format(font=FONT.as_uri(), size=size, gap=round(size * 0.9),
                               fsize=round(size * 1.05), body=body, domain=post["domain"])
            tmp = out / f"_{name}.html"
            tmp.write_text(html, encoding="utf-8")
            pg.goto(tmp.as_uri())
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(300)
            pg.screenshot(path=str(out / f"{name}.jpg"), type="jpeg", quality=92)
            tmp.unlink()
        b.close()
    print("rendered", out / "img1.jpg", out / "img2.jpg")


def call(method, url, params):
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        req = urllib.request.Request(url + "?" + data.decode())
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url.split('?')[0]} -> {e.code}: {body}") from None


def image_urls(pid):
    base = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/posts/{pid}"
    return [f"{base}/img1.jpg", f"{base}/img2.jpg"]


def wait_ig(host, cid, tok):
    for _ in range(30):
        s = call("GET", f"{host}/{cid}", {"fields": "status_code", "access_token": tok}).get("status_code")
        if s == "FINISHED":
            return
        if s == "ERROR":
            raise RuntimeError(f"IG container {cid} failed")
        time.sleep(5)
    raise RuntimeError(f"IG container {cid} timed out")


def publish_ig(pid):
    post, tok, uid = load(pid), os.environ["IG_ACCESS_TOKEN"], os.environ["IG_USER_ID"]
    last = None
    for host in (FB, IGH):  # system-user tokens use graph.facebook.com; IG-login tokens use graph.instagram.com
        try:
            kids = [call("POST", f"{host}/{uid}/media", {"image_url": u, "is_carousel_item": "true", "access_token": tok})["id"]
                    for u in image_urls(pid)]
            for k in kids:
                wait_ig(host, k, tok)
            car = call("POST", f"{host}/{uid}/media", {"media_type": "CAROUSEL", "children": ",".join(kids),
                                                       "caption": post["caption"], "access_token": tok})["id"]
            wait_ig(host, car, tok)
            res = call("POST", f"{host}/{uid}/media_publish", {"creation_id": car, "access_token": tok})
            print("IG published:", res, "via", host)
            return
        except RuntimeError as e:
            last = e
            print("IG attempt via", host, "failed:", e)
    raise last


def publish_threads(pid):
    """Threads: the love line is the post itself; a plain-text self-reply explains the knowledge (no images)."""
    post, tok = load(pid), os.environ["THREADS_ACCESS_TOKEN"]
    main = {"media_type": "TEXT", "text": post["threads_main"], "access_token": tok}
    if post.get("topic_tag"):
        main["topic_tag"] = post["topic_tag"]
    cid = call("POST", f"{TH}/me/threads", main)["id"]
    time.sleep(10)
    main_id = call("POST", f"{TH}/me/threads_publish", {"creation_id": cid, "access_token": tok})["id"]
    print("Threads main post published:", main_id)
    reply = {"media_type": "TEXT", "text": post["threads_reply"], "reply_to_id": main_id, "access_token": tok}
    rid = call("POST", f"{TH}/me/threads", reply)["id"]
    time.sleep(30)
    res = call("POST", f"{TH}/me/threads_publish", {"creation_id": rid, "access_token": tok})
    print("Threads reply published:", res)


if __name__ == "__main__":
    cmd, pid = sys.argv[1], sys.argv[2]
    if cmd == "render":
        render(pid)
    elif cmd == "publish":
        target = sys.argv[3] if len(sys.argv) > 3 else "both"
        errors = []
        for name, fn in (("ig", publish_ig), ("threads", publish_threads)):
            if target in (name, "both"):
                try:
                    fn(pid)
                except Exception as e:
                    errors.append(f"{name}: {e}")
        if errors:
            sys.exit("\n".join(errors))
