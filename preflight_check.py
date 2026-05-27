"""Full pre-flight check before scheduled cron runs."""
import sqlite3
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TODAY = date.today().isoformat()
CHANNEL_ID = "page_1"

print("=" * 60)
print(f"PRE-FLIGHT CHECK — {TODAY}")
print("=" * 60)

issues = []
warnings = []

# ── 1. DB STATE ───────────────────────────────────────────────
print("\n[1] Database state")
con = sqlite3.connect("data/automation.db")
con.row_factory = sqlite3.Row

runs = con.execute(
    "SELECT slot, status FROM runs WHERE channel_id=? AND run_date=? ORDER BY slot",
    (CHANNEL_ID, TODAY)
).fetchall()

slots_ran_today = {r["slot"]: r["status"] for r in runs}
print(f"  Slots ran today: {dict(slots_ran_today)}")

for slot in [1, 2, 3]:
    if slot in slots_ran_today:
        issues.append(f"Slot {slot} ALREADY RAN today (status={slots_ran_today[slot]}) — cron will SKIP it!")
    else:
        print(f"  ✅ Slot {slot} — clear, cron will run")

posted = con.execute(
    "SELECT source_video_id FROM posted_videos WHERE channel_id=?", (CHANNEL_ID,)
).fetchall()
posted_ids = {r["source_video_id"] for r in posted}
print(f"  Posted videos total: {len(posted_ids)}")

retries = con.execute(
    "SELECT source_video_id, retry_count, next_retry_date, error_message FROM video_retries WHERE channel_id=?",
    (CHANNEL_ID,)
).fetchall() if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='video_retries'").fetchone() else []
if retries:
    print(f"  Retry queue: {len(retries)} video(s)")
    for r in retries:
        print(f"    - {r['source_video_id']} | retries={r['retry_count']} | next={r['next_retry_date']} | err={r['error_message'][:50]}")
else:
    print(f"  ✅ Retry queue — empty")

con.close()

# ── 2. CREDENTIALS & TOKENS ───────────────────────────────────
print("\n[2] Credentials & tokens")
try:
    dest_creds = json.loads((ROOT / "credentials/page_1_dest_credentials.json").read_text())
    dest_token = json.loads((ROOT / "tokens/page_1_dest_token.json").read_text())
    src_creds  = json.loads((ROOT / "credentials/page_1_source_credentials.json").read_text())
    src_token  = json.loads((ROOT / "tokens/page_1_source_token.json").read_text())
    print(f"  ✅ All 4 credential/token files present")
    print(f"  Dest app_id: {dest_creds.get('app_id')} | page_id: {dest_creds.get('page_id')}")
    print(f"  Source page_id: {src_creds.get('page_id')}")

    for label, token_data in [("Source", src_token), ("Dest", dest_token)]:
        expires = token_data.get("expires_at", "unknown")
        if expires != "unknown":
            exp_date = date.fromisoformat(expires)
            days_left = (exp_date - date.today()).days
            if days_left < 0:
                issues.append(f"{label} token EXPIRED {abs(days_left)} days ago!")
            elif days_left <= 7:
                warnings.append(f"{label} token expires in {days_left} days — refresh soon")
            else:
                print(f"  ✅ {label} token — expires {expires} ({days_left} days left)")
        else:
            warnings.append(f"{label} token has no expiry date stored")

    if not dest_token.get("page_access_token"):
        issues.append("Dest page_access_token is missing!")
    else:
        print(f"  ✅ Dest page_access_token — present")

except FileNotFoundError as e:
    issues.append(f"Missing file: {e}")

# ── 3. SOURCE VIDEOS AVAILABLE ────────────────────────────────
print("\n[3] Source videos — checking Walter Hayes via API (same logic as bot)")
try:
    from src.fb_source import get_source_videos
    src_page_id = src_creds["page_id"]
    src_tok = src_token["page_access_token"]
    all_videos = get_source_videos(src_page_id, src_tok)  # fetches ALL pages, oldest-first
    if all_videos is None:
        issues.append("Could not reach Walter Hayes — network or permission error")
    else:
        unposted = [v for v in all_videos if v["id"] not in posted_ids]
        print(f"  Total videos on Walter Hayes: {len(all_videos)}")
        print(f"  Already posted: {len(posted_ids)}")
        print(f"  Unposted (available): {len(unposted)}")
        if len(unposted) < 3:
            issues.append(f"Only {len(unposted)} unposted videos available — need 3 for today's slots!")
        else:
            print(f"  ✅ Enough videos — next 3 slots will pick:")
            for i, v in enumerate(unposted[:3], 1):
                length = v.get('length', 0)
                orient = "Portrait/Reel" if v.get("height", 0) > v.get("width", 0) else "Landscape"
                print(f"    Slot {i}: {v['id']} | {length}s | {orient} | created {str(v.get('created_time','?'))[:10]}")
except Exception as e:
    issues.append(f"Could not fetch source videos: {e}")

# ── 4. DEST PAGE REACHABLE ────────────────────────────────────
print("\n[4] Destination page (Walt Goodman) reachability")
try:
    resp = requests.get(
        f"https://graph.facebook.com/v19.0/{dest_creds['page_id']}",
        params={"fields": "id,name,fan_count", "access_token": dest_token["page_access_token"]},
        timeout=15
    )
    resp.raise_for_status()
    page_data = resp.json()
    if "error" in page_data:
        issues.append(f"Dest page error: {page_data['error']}")
    else:
        print(f"  ✅ {page_data.get('name')} (ID: {page_data.get('id')}) — {page_data.get('fan_count', '?')} followers")
except Exception as e:
    issues.append(f"Dest page unreachable: {e}")

# ── 5. SCHEDULING TIMES ───────────────────────────────────────
print("\n[5] Scheduled publish times")
slot_times = {1: "13:00", 2: "15:00", 3: "17:00"}
now_utc = datetime.now(timezone.utc)
print(f"  Current UTC: {now_utc.strftime('%H:%M')}")
for slot, t in slot_times.items():
    h, m = map(int, t.split(":"))
    target = now_utc.replace(hour=h, minute=m, second=0, microsecond=0)
    delta_min = (target - now_utc).total_seconds() / 60
    cron_fires_min = delta_min - 15
    if delta_min < 0:
        status = "PAST — will publish immediately if run now"
    elif cron_fires_min < 0:
        status = f"Cron already fired, {delta_min:.0f} min to go live"
    else:
        status = f"Cron fires in {cron_fires_min:.0f} min | goes live in {delta_min:.0f} min"
    print(f"  Slot {slot} ({t} UTC): {status}")

# ── SUMMARY ───────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
if not issues and not warnings:
    print("✅ ALL CLEAR — system ready for today's scheduled runs")
else:
    if issues:
        print(f"\n🚨 ISSUES ({len(issues)}) — must fix:")
        for i in issues:
            print(f"   ✗ {i}")
    if warnings:
        print(f"\n⚠  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"   ! {w}")
