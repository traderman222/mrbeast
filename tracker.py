import os
import csv
import time
import json
from googleapiclient.discovery import build
import isodate

# ---- CONFIG ----
API_KEY = os.getenv("YOUTUBE_API_KEY")  # GitHub Actions secret
CHANNEL_ID = "UCX6OQ3DkcsbYNE6H8uQQuVA"  # MrBeast
OUTPUT_FILE = "mrbeast_views.csv"
CACHE_FILE = "videos_cache.json"
MAX_TRACKED_VIDEOS = 16  # Quota safe limit

# ---- YOUTUBE API CLIENT ----
youtube = build("youtube", "v3", developerKey=API_KEY)


def iso8601_duration_to_seconds(duration):
    return int(isodate.parse_duration(duration).total_seconds())


def load_cache():
    if os.path.isfile(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_uploads_playlist_id():
    """Fetch uploads playlist ID once (can be cached forever)."""
    channel_resp = youtube.channels().list(
        part="contentDetails", id=CHANNEL_ID
    ).execute()
    return channel_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_latest_video_ids(playlist_id, max_results=50):
    """Fetch up to 50 latest uploads (IDs only)."""
    playlist_resp = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=playlist_id,
        maxResults=max_results
    ).execute()
    return [item["contentDetails"]["videoId"] for item in playlist_resp["items"]]

def fetch_video_metadata(video_ids):
    """Fetch title + duration + published date for given videos."""
    if not video_ids:
        return {}

    resp = youtube.videos().list(
        part="contentDetails,snippet",
        id=",".join(video_ids)
    ).execute()

    meta = {}
    for item in resp["items"]:
        duration = iso8601_duration_to_seconds(item["contentDetails"]["duration"])
        published_at = item["snippet"]["publishedAt"]
        meta[item["id"]] = {
            "title": item["snippet"]["title"],
            "duration": duration,
            "publishedAt": published_at,
        }
    return meta

def fetch_video_stats(video_ids):
    """Fetch just statistics (cheaper)."""
    resp = youtube.videos().list(
        part="statistics",
        id=",".join(video_ids)
    ).execute()

    stats = {}
    for item in resp["items"]:
        s = item["statistics"]
        stats[item["id"]] = {
            "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0))
        }
    return stats


def save_views(rows):
    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "video_id", "views", "likes", "comments"])
        writer.writerows(rows)


def main():
    cache = load_cache()
    playlist_id = cache.get("_uploads_playlist")

    # fetch uploads playlist only once
    if not playlist_id:
        playlist_id = get_uploads_playlist_id()
        cache["_uploads_playlist"] = playlist_id
        save_cache(cache)

    # get up to 50 latest uploads
    latest_ids = get_latest_video_ids(playlist_id, max_results=50)

    # detect new videos
    new_ids = [vid for vid in latest_ids if vid not in cache]

    # detect old videos missing metadata (retroactive fix)
    missing_meta_ids = [
        vid for vid in cache
        if vid not in ("_uploads_playlist",) and
           ("publishedAt" not in cache[vid] or "title" not in cache[vid] or "duration" not in cache[vid])
    ]

    ids_to_fetch = new_ids + missing_meta_ids
    if ids_to_fetch:
        meta = fetch_video_metadata(ids_to_fetch)
        for vid, m in meta.items():
            # only track if not shorts (< 3 min)
            if m["duration"] >= 3 * 60:
                if vid in cache:
                    cache[vid].update(m)  # update missing fields
                else:
                    cache[vid] = m
        save_cache(cache)

    # filter long-form videos and limit to the most recent MAX_TRACKED_VIDEOS
    tracked_ids = [
        vid for vid in latest_ids
        if vid in cache and cache[vid]["duration"] >= 3 * 60
    ][:MAX_TRACKED_VIDEOS]

    if not tracked_ids:
        print("No long-form videos to track.")
        return

    # fetch stats for tracked videos
    stats = fetch_video_stats(tracked_ids)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for vid in tracked_ids:
        vstats = stats.get(vid, {})
        rows.append([
            timestamp, vid,
            vstats.get("views", 0),
            vstats.get("likes", 0),
            vstats.get("comments", 0)
        ])

    save_views(rows)
    print(f"Saved {len(rows)} entries at {timestamp}")

if __name__ == "__main__":
    main()
