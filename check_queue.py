from src.config import load_config, load_credentials, load_token
from src.fb_source import get_source_videos, is_short_video
from src.db import get_posted_video_ids

cfg = load_config()
for ch in cfg['channels']:
    creds = load_credentials(ch['source_credentials_file'])
    token = load_token(ch['source_token_file'])
    videos = get_source_videos(creds['page_id'], token['page_access_token'])
    posted = get_posted_video_ids(ch['id'])
    unposted = [v for v in videos if v['id'] not in posted]
    next3 = unposted[:3]
    print(f"\n{ch['id']} ({ch['source_page_name']} -> {ch['dest_page_name']}):")
    for i, v in enumerate(next3, 1):
        reel = is_short_video(v.get('length'), ch.get('shorts_max_seconds', 180), v.get('width', 0), v.get('height', 0))
        w, h = v.get('width', 0), v.get('height', 0)
        print(f"  Slot {i}: {v['id']} | {v.get('views',0):,} views | {int(v.get('length') or 0)}s | {w}x{h} | reel={reel}")
