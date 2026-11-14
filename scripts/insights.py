"""Read-only: pull IG + Threads insights for every published post and the account.

Writes insights.json (raw) and prints a markdown summary. Never posts anything.
Each metric is requested on its own, so one unsupported metric or missing
permission only blanks that cell instead of failing the whole run.
Error messages are printed without the access token.
"""
import json, os, sys, time, pathlib, urllib.request, urllib.parse, urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOSTS = ["https://graph.facebook.com/v25.0", "https://graph.instagram.com/v25.0"]
TH = "https://graph.threads.net/v1.0"
IG_TOK, IG_UID = os.environ.get("IG_ACCESS_TOKEN", ""), os.environ.get("IG_USER_ID", "")
TH_TOK = os.environ.get("THREADS_ACCESS_TOKEN", "")
errors = []


def get(url, params, tok):
    q = urllib.parse.urlencode({**params, "access_token": tok})
    try:
        with urllib.request.urlopen(f"{url}?{q}", timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("message", "")
        except Exception:
            msg = str(e.code)
        return {"_error": msg[:200]}
    except Exception as e:  # network
        return {"_error": type(e).__name__}


def val(resp):
    if "_error" in resp:
        return None, resp["_error"]
    d = resp.get("data") or []
    if not d:
        return None, "empty"
    m = d[0]
    if "total_value" in m:
        tv = m["total_value"]
        if tv.get("breakdowns"):
            return {r["dimension_values"][0]: r["value"] for b in tv["breakdowns"] for r in b["results"]}, None
        return tv.get("value"), None
    vs = m.get("values") or []
    return (vs[-1].get("value") if vs else None), None


# pick the IG host that works with this token
IGH = None
for h in HOSTS:
    if "_error" not in get(f"{h}/{IG_UID}", {"fields": "username"}, IG_TOK):
        IGH = h
        break
if not IGH:
    errors.append("IG: 兩個 API 網域都無法用這個權杖讀帳號")

POST_METRICS = ["reach", "views", "saved", "shares", "likes", "comments", "total_interactions", "profile_visits", "follows"]
TH_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
out = {"posts": {}, "account": {}, "threads_account": {}}

for d in sorted((ROOT / "posts").iterdir()):
    sf = d / "status.json"
    if not sf.exists():
        continue
    st = json.loads(sf.read_text(encoding="utf-8"))
    row = {"published_at": st.get("ig", {}).get("at"), "ig": {}, "threads": {}}
    if IGH and "ig" in st:
        for m in POST_METRICS:
            v, err = val(get(f"{IGH}/{st['ig']['id']}/insights", {"metric": m}, IG_TOK))
            row["ig"][m] = v
            if err and err != "empty":
                errors.append(f"IG {d.name} {m}: {err}")
    if TH_TOK and "threads" in st:
        for m in TH_METRICS:
            v, err = val(get(f"{TH}/{st['threads']['id']}/insights", {"metric": m}, TH_TOK))
            row["threads"][m] = v
            if err and err != "empty":
                errors.append(f"TH {d.name} {m}: {err}")
    out["posts"][d.name] = row

now = int(time.time())
since = now - 28 * 86400 + 60
if IGH:
    for m, extra in [("reach", {"breakdown": "follow_type"}), ("reach", {}), ("views", {}), ("accounts_engaged", {}),
                     ("total_interactions", {}), ("profile_links_taps", {}), ("follows_and_unfollows", {"breakdown": "follow_type"})]:
        key = m + ("_by_" + extra["breakdown"] if extra else "")
        v, err = val(get(f"{IGH}/{IG_UID}/insights", {"metric": m, "period": "day", "metric_type": "total_value",
                                                      "since": since, "until": now, **extra}, IG_TOK))
        out["account"][key] = v
        if err:
            errors.append(f"IG account {key}: {err}")
    prof = get(f"{IGH}/{IG_UID}", {"fields": "followers_count,media_count"}, IG_TOK)
    out["account"]["profile"] = {k: prof.get(k) for k in ("followers_count", "media_count")}
    # daily follower_count (only last 30 days supported)
    fc = get(f"{IGH}/{IG_UID}/insights", {"metric": "follower_count", "period": "day", "since": since, "until": now}, IG_TOK)
    out["account"]["follower_count_daily"] = [(x["end_time"][:10], x["value"]) for x in (fc.get("data") or [{}])[0].get("values", [])] if "_error" not in fc else fc["_error"]

if TH_TOK:
    for m in ["views", "likes", "replies", "reposts", "quotes", "followers_count"]:
        v, err = val(get(f"{TH}/me/threads_insights", {"metric": m, "since": since, "until": now}, TH_TOK))
        if m == "views" and v is None and not err:
            pass
        out["threads_account"][m] = v
        if err:
            errors.append(f"TH account {m}: {err}")

out["errors"] = errors
(ROOT / "insights.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

# markdown summary
L = ["## IG 單篇", "| 篇 | 觸及 | 觀看 | 收藏 | 分享 | 讚 | 留言 | 主頁瀏覽 | 追蹤 |", "|" + "---|" * 9]
for pid, r in out["posts"].items():
    g = r["ig"]
    L.append(f"| {pid} | " + " | ".join(str(g.get(k, "")) for k in ["reach", "views", "saved", "shares", "likes", "comments", "profile_visits", "follows"]) + " |")
L += ["", "## Threads 單篇", "| 篇 | 觀看 | 讚 | 回覆 | 轉發 | 引用 | 分享 |", "|" + "---|" * 7]
for pid, r in out["posts"].items():
    t = r["threads"]
    L.append(f"| {pid} | " + " | ".join(str(t.get(k, "")) for k in TH_METRICS) + " |")
L += ["", "## 帳號（近 28 天）", "```", json.dumps(out["account"], ensure_ascii=False, indent=1),
      json.dumps(out["threads_account"], ensure_ascii=False, indent=1), "```", "", f"## 錯誤（{len(errors)}）"] + [f"- {e}" for e in errors[:60]]
md = "\n".join(L)
print(md)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
        f.write(md + "\n")
