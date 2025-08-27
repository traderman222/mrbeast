import os
import csv
import time
from googleapiclient.discovery import build
import isodate

# ---- CONFIG ----
API_KEY = os.getenv("YOUTUBE_API_KEY")  # Read from GitHub Actions secret
CHANNEL_ID = "UCX6OQ3DkcsbYNE6H8uQQuVA"  # MrBeast's channel ID
OUTPUT_FILE = "mrbeast_views.csv"

# ---- YOUTUBE API CLIENT ----
youtube = build("youtube", "v3", developerKey=API_KEY)


def iso8601_duration_to_seconds(duration):
    return int(isodate.parse_duration(duration).total_seconds())


def get_latest_non_shorts_videos():
    # Get uploads playlist ID
    channel_resp = youtube.channels().list(
        part="contentDetails", id=CHANNEL_ID
    ).execute()
    uploads_playlist = channel_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # Fetch latest 30 videos (maxResults = 30)
    playlist_resp = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_playlist,
        maxResults=30
    ).execute()

    video_ids = [item["contentDetails"]["videoId"] for item in playlist_resp["items"]]

    # Get video details
    video_resp = youtube.videos().list(
        part="contentDetails,statistics,snippet",
        id=",".join(video_ids)
    ).execute()

    # Filter out shorts (duration < 60s)
    videos = []
    for item in video_resp["items"]:
        duration = item["contentDetails"]["duration"]
        seconds = iso8601_duration_to_seconds(duration)
        if seconds >= 3 * 60:
            stats = item["statistics"]
            videos.append({
                "title": item["snippet"]["title"],
                "id": item["id"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0))
            })

    return videos


def save_views():
    videos = get_latest_non_shorts_videos()
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    file_exists = os.path.isfile(OUTPUT_FILE)
    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "video_id", "title", "views", "likes", "comments"])
        for v in videos:
            writer.writerow([timestamp, v["id"], v["title"], v["views"], v["likes"], v["comments"]])

    print(f"Saved {len(videos)} entries at {timestamp}")


if __name__ == "__main__":
    save_views()
