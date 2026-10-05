# ⚡ Omni Downloader Backend API Documentation

Welcome to the official developer and AI agent reference for the **Omni Media Downloader Backend (XDOWNDERBACKEND)**.  
This document specifies every endpoint, accepted parameters, query schemas, and **exact raw JSON responses** so your frontend AI agent (e.g. Cursor, v0, Claude, ChatGPT) or human developer can seamlessly bind UI components, state machines, and TypeScript interfaces.

---

## 🌐 1. Server Configuration & Base URL

| Environment | Base URL |
| :--- | :--- |
| **Production (Render Live)** | `https://xdownderbackend.onrender.com` |
| **Local Development** | `http://localhost:5000` (or `http://localhost:5001`) |

- **CORS Policy**: Enabled globally (`Access-Control-Allow-Origin: *`). Frontend applications can directly call endpoints via browser `fetch`, `axios`, or TanStack React Query without CORS issues.
- **Request Ingestion**: Every media extraction route dynamically supports:
  1. `GET` with Query Parameters: `?url=https://...`
  2. `POST` with JSON Body: `{"url": "https://..."}`
  3. `POST` with Form-Data / x-www-form-urlencoded: `url=https://...`
- **Encoding Rule**: When forwarding URLs into proxy or query parameters (such as `/api/download?url=...`), always wrap the target link in `encodeURIComponent(url)`.

---

## 📑 2. Quick Route Index

| Category | Endpoint | Methods | Primary Output |
| :--- | :--- | :--- | :--- |
| **System** | `/health` | `GET` | Health status, version, port |
| **Index** | `/` or `/api/services` | `GET` | Catalog of available routes |
| **Universal Dispatcher** | `/api/general` (alias: `/api/universal`) | `GET`, `POST` | Auto-detects platform & returns media payload |
| **Facebook** | `/api/facebook` (alias: `/api/fb`) | `GET`, `POST` | HD video direct stream & proxy link |
| **Instagram Universal** | `/api/instagram` | `GET`, `POST` | Auto-dispatches Post, Reel, Story, or Profile |
| **Instagram Reel / Post**| `/api/instagram/post` (alias: `/reel`) | `GET`, `POST` | Single video/photo or carousel sidecars |
| **Instagram Story** | `/api/instagram/story` | `GET`, `POST` | Active user stories |
| **Instagram Highlight**| `/api/instagram/highlight` | `GET`, `POST` | Saved highlight album items |
| **Instagram Profile** | `/api/instagram/profile` | `GET`, `POST` | Avatar, follower count, bio, stats |
| **YouTube** | `/api/youtube` (alias: `/api/yt`) | `GET`, `POST` | 144p–4K MP4 formats + M4A audio streams |
| **YouTube File** | `/api/youtube/download` | `GET`, `POST` | Direct MP4 binary file attachment stream |
| **Spotify** | `/api/spotify` | `GET`, `POST` | 320kbps MP3 direct download links |
| **Apple Music** | `/api/apple` (alias: `/api/apple-music`) | `GET`, `POST` | Direct MP3 streams & cover artwork |
| **TeraBox** | `/api/terabox` | `GET`, `POST` | File tree, sizes, fast streaming link |
| **TeraBox File** | `/api/terabox/download` | `GET` | Chunked binary proxy download stream |
| **TikTok** | `/api/tiktok` | `GET`, `POST` | Watermark-free video direct URL |
| **Snapchat** | `/api/snapchat` (alias: `/api/snap`) | `GET`, `POST` | Spotlight & public story stream URL |
| **Twitter / X** | `/api/twitter` (alias: `/api/x`) | `GET`, `POST` | MP4 video resolutions & thumbnail |
| **Stream Proxy** | `/api/download` | `GET` | Direct browser attachment download |

---

## 🔍 3. Endpoints & Exact Raw Responses

### 3.1. System Health Check
**Endpoint**: `GET /health`  
Returns server operational status, port, and active version.

#### Raw Response:
```json
{
  "port": 10000,
  "status": "healthy",
  "timestamp": 1791168372,
  "version": "7.0.0-XDOWNDERBACKEND"
}
```

---

### 3.2. Service Catalog & Directory
**Endpoint**: `GET /` or `GET /api/services`  
Returns route map and API greeting.

#### Raw Response:
```json
{
  "endpoints": {
    "apple_music": "/api/apple?url={apple_music_url}",
    "facebook": "/api/facebook?url={facebook_video_url}",
    "health": "/health",
    "instagram": "/api/instagram?url={post_or_reel_url}",
    "services": "/api/services",
    "snapchat": "/api/snapchat?url={snapchat_url}",
    "spotify": "/api/spotify?url={track_or_album_url}",
    "terabox": "/api/terabox?url={terabox_url}",
    "tiktok": "/api/tiktok?url={tiktok_url}",
    "twitter_x": "/api/twitter?url={tweet_or_x_url}",
    "universal": "/api/general?url={media_url}",
    "youtube": "/api/youtube?url={video_or_shorts_url}"
  },
  "message": "Welcome to XDOWNDERBACKEND API. Use /api/general?url={url} for universal extraction or service-specific endpoints.",
  "service": "XDOWNDERBACKEND Universal API",
  "status": "online",
  "version": "7.0.0-XDOWNDERBACKEND"
}
```

---

### 3.3. Universal Media Dispatcher
**Endpoint**: `GET /api/general?url=<media_url>` or `POST /api/general`  
**Alias**: `/api/universal`  
Smart routing engine: automatically inspects any media URL (Facebook, Instagram, YouTube, Spotify, Apple Music, TeraBox, TikTok, Snapchat, Twitter/X) and invokes the optimal extraction pipeline.

#### Request Example (POST):
```bash
POST https://xdownderbackend.onrender.com/api/general
Content-Type: application/json

{
  "url": "https://www.facebook.com/watch/?v=10153231379946729"
}
```

#### Raw Response:
```json
{
  "status": "ok",
  "platform": "facebook",
  "title": "2.8M views · 1.2K reactions | How to share with just friends. | Facebook",
  "author": "Facebook",
  "quality": "HD",
  "duration": null,
  "thumbnail": "https://scontent-kul2-1.xx.fbcdn.net/v/t39.30808-1/380700650_10162533193146729_2379134611963304810_n.jpg?stp=cp0_dst-jpg_tt6&oh=00_AQMMcBPrGMVDjDolkPB1Eu-HYkF4Gi9kwOSMbok6m-IxOQ&oe=6AC8F34E",
  "sourceUrl": "https://www.facebook.com/watch/?v=10153231379946729",
  "directUrl": "https://video-kul3-1.xx.fbcdn.net/o1/v/t2/f2/m412/AQO00w7gkHtBwvAKd2SCYhroaNCqSwBQ52S2KsO2HwmohEiR_GoAwy8VIVzshQP4cIHoXexac9D3IR_1OBxPgGE.mp4?oh=00_AQMV5EC9P5xZrdlAQ5hnEzld2nbzS61uJE_1VfH3qFY48g&oe=6AC8E59D&bitrate=580000&tag=hd",
  "downloadUrl": "https://xdownderbackend.onrender.com/api/download?url=https%3A%2F%2Fvideo-kul3-1.xx.fbcdn.net%2Fo1%2Fv%2Ft2%2Ff2%2Fm412%2FAQO00w7gkHtBwvAKd2SCYhroaNCqSwBQ52S2KsO2HwmohEiR_GoAwy8VIVzshQP4cIHoXexac9D3IR_1OBxPgGE.mp4...&filename=facebook-video.mp4",
  "engine": "cloud-primary"
}
```

---

### 3.4. Facebook Video & Reels
**Endpoint**: `GET /api/facebook?url=<fb_url>` or `POST /api/facebook`  
**Alias**: `/api/fb`

#### Raw Response:
```json
{
  "status": "ok",
  "platform": "facebook",
  "title": "2.8M views · 1.2K reactions | How to share with just friends. | Facebook",
  "author": "Facebook",
  "quality": "HD",
  "duration": null,
  "thumbnail": "https://scontent-kul2-1.xx.fbcdn.net/v/t39.30808-1/380700650_10162533193146729_2379134611963304810_n.jpg?stp=cp0_dst-jpg_tt6&oh=00_AQMMcBPrGMVDjDolkPB1Eu-HYkF4Gi9kwOSMbok6m-IxOQ&oe=6AC8F34E",
  "sourceUrl": "https://www.facebook.com/watch/?v=10153231379946729",
  "directUrl": "https://video-kul3-1.xx.fbcdn.net/o1/v/t2/f2/m412/AQO00w7gkHtBwvAKd2SCYhroaNCqSwBQ52S2KsO2HwmohEiR_GoAwy8VIVzshQP4cIHoXexac9D3IR_1OBxPgGE.mp4?oh=00_AQMV5EC9P5xZrdlAQ5hnEzld2nbzS61uJE_1VfH3qFY48g&oe=6AC8E59D&bitrate=580000&tag=hd",
  "downloadUrl": "https://xdownderbackend.onrender.com/api/download?url=https%3A%2F%2Fvideo-kul3-1.xx.fbcdn.net...",
  "engine": "cloud-primary"
}
```

---

### 3.5. Instagram Endpoints

#### A. Post & Reel (`GET /api/instagram/post?url=...` or `POST /api/instagram/post`)
**Alias**: `/api/instagram/reel` or `/api/instagram?url=...`  
Extracts single video, single photo, or carousel sidecars.

##### Primary Cloud Engine Format (Single Video/Reel):
```json
{
  "status": "ok",
  "platform": "instagram",
  "title": "Instagram Reel",
  "author": "instagram_creator",
  "thumbnail": "https://instagram.fdel1-1.fna.fbcdn.net/v/t51.2885-15/...",
  "quality": "HD",
  "duration": null,
  "sourceUrl": "https://www.instagram.com/reel/C8qG0n_M00G/",
  "directUrl": "https://instagram.fdel1-1.fna.fbcdn.net/o1/v/t2/f2/...",
  "downloadUrl": "https://xdownderbackend.onrender.com/api/download?url=https%3A%2F%2Finstagram.fdel1-1.fna.fbcdn.net...",
  "engine": "cloud-primary"
}
```

##### Native Instaloader / Carousel Format (when multiple slides):
```json
{
  "status": "success",
  "platform": "instagram",
  "shortcode": "C8qG0n_M00G",
  "type": "carousel",
  "owner": "creator_username",
  "likes": 54200,
  "caption": "Check out this amazing photo set!",
  "media_count": 2,
  "media": [
    {
      "index": 1,
      "type": "video",
      "format": "mp4",
      "label": "Slide 1 (Video)",
      "url": "https://scontent.cdninstagram.com/v/t50.2886-16/..."
    },
    {
      "index": 2,
      "type": "image",
      "format": "jpg",
      "label": "Slide 2 (Image)",
      "url": "https://scontent.cdninstagram.com/v/t51.2885-15/..."
    }
  ],
  "extracted_in_seconds": 1.45
}
```

#### B. User Story (`GET /api/instagram/story?username=<user>`)
```json
{
  "status": "success",
  "platform": "instagram",
  "type": "story",
  "username": "natgeo",
  "media_count": 2,
  "media": [
    {
      "index": 1,
      "media_id": "3128471928471",
      "type": "video",
      "format": "mp4",
      "timestamp": "2026-10-05T07:15:00Z",
      "label": "Story 1 (07:15)",
      "url": "https://scontent.cdninstagram.com/v/..."
    }
  ],
  "extracted_in_seconds": 2.1
}
```

#### C. User Profile (`GET /api/instagram/profile?username=<user>`)
```json
{
  "status": "success",
  "platform": "instagram",
  "type": "profile",
  "username": "google",
  "full_name": "Google",
  "followers": 15400000,
  "following": 42,
  "total_posts": 2814,
  "is_verified": true,
  "is_private": false,
  "profile_pic_hd_url": "https://instagram.fdel1-1.fna.fbcdn.net/...",
  "extracted_in_seconds": 0.8
}
```

---

### 3.6. YouTube Video & Audio Formats
**Endpoint**: `GET /api/youtube?url=<youtube_url>` or `POST /api/youtube`  
**Alias**: `/api/yt`  
Resolves all available MP4/WebM video resolutions (144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p 4K) and direct audio streams using PyTubeFix bot-detection bypass.

#### Raw Response:
```json
{
  "status": "success",
  "platform": "youtube",
  "mode": "all_formats",
  "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)",
  "uploader": "Rick Astley",
  "duration_seconds": 213,
  "format": "mp4",
  "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hq720.jpg",
  "available_resolutions": [
    "2160p",
    "1440p",
    "1080p",
    "720p",
    "480p",
    "360p",
    "240p",
    "144p",
    "audio_only"
  ],
  "primary_stream_url": "https://rr5---sn-gwpa-25uey.googlevideo.com/videoplayback?expire=...",
  "primary_audio_url": "https://rr5---sn-gwpa-25uey.googlevideo.com/videoplayback?expire=...",
  "total_video_qualities": 9,
  "total_audio_streams": 6,
  "video_formats": [
    {
      "format_id": "313",
      "format_note": "video only",
      "ext": "webm",
      "quality": "2160p",
      "resolution": "2160p",
      "fps": 25,
      "vcodec": "vp9",
      "acodec": null,
      "has_video": true,
      "has_audio": false,
      "bitrate_kbps": 18076.6,
      "filesize_bytes": 481290433,
      "filesize": "458.99 MB",
      "url": "https://rr5---sn-gwpa-25uey.googlevideo.com/videoplayback?..."
    },
    {
      "format_id": "18",
      "format_note": "progressive",
      "ext": "mp4",
      "quality": "360p",
      "resolution": "360p",
      "fps": 25,
      "vcodec": "avc1.42001E",
      "acodec": "mp4a.40.2",
      "has_video": true,
      "has_audio": true,
      "bitrate_kbps": 612.4,
      "filesize_bytes": 16300122,
      "filesize": "15.54 MB",
      "url": "https://rr5---sn-gwpa-25uey.googlevideo.com/videoplayback?..."
    }
  ],
  "audio_formats": [
    {
      "format_id": "251",
      "format_note": "audio only",
      "ext": "webm",
      "quality": "audio_only",
      "resolution": "audio only",
      "bitrate_kbps": 136.5,
      "filesize_bytes": 3635484,
      "filesize": "3.47 MB",
      "has_audio": true,
      "has_video": false,
      "url": "https://rr5---sn-gwpa-25uey.googlevideo.com/videoplayback?..."
    }
  ],
  "extracted_in_seconds": 2.1
}
```

#### YouTube Binary Download File (`GET /api/youtube/download`):
- **Parameters**: `?url=<youtube_url>&resolution=360p` or `&resolution=720p`
- **Output**: Binary MP4 file attachment stream (`Content-Disposition: attachment; filename="Never Gonna Give You Up_360p.mp4"`).

---

### 3.7. Spotify 320kbps MP3 Extractor
**Endpoint**: `GET /api/spotify?url=<spotify_track_or_album>` or `POST /api/spotify`  
Resolves high-quality MP3 download links for single tracks, full albums, or playlists.

#### Raw Response:
```json
{
  "status": "success",
  "platform": "spotify",
  "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
  "total_tracks": 1,
  "tracks": [
    {
      "title": "Never Gonna Give You Up",
      "artist": "Rick Astley",
      "album": "Whenever You Need Somebody",
      "release_date": "1987-11-12",
      "duration_seconds": 213,
      "duration_ms": 213573,
      "cover": "https://i.scdn.co/image/ab67616d0000b2735755e164993798e0c9ef7d7a",
      "spotify_url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
      "download_url": "https://rapid.spotidown.app/v2?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    }
  ]
}
```

---

### 3.8. Apple Music Extractor
**Endpoint**: `GET /api/apple?url=<apple_music_url>` or `POST /api/apple`  
**Alias**: `/api/apple-music`

#### Raw Response:
```json
{
  "status": "success",
  "platform": "apple_music",
  "type": "song",
  "title": "Blinding Lights",
  "artist": "The Weeknd",
  "album": "After Hours",
  "total_tracks": 1,
  "tracks": [
    {
      "index": 1,
      "title": "Blinding Lights",
      "artist": "The Weeknd",
      "duration": "3:20",
      "cover": "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/...",
      "download_url": "https://rapid.spotidown.app/v2?token=..."
    }
  ],
  "extracted_in_seconds": 1.2
}
```

---

### 3.9. TeraBox File & Folder Extractor
**Endpoint**: `GET /api/terabox?url=<terabox_url>` or `POST /api/terabox`

#### Raw Response:
```json
{
  "status": "success",
  "platform": "terabox",
  "shareid": "192847192",
  "uk": "29184719",
  "title": "Shared Media Folder",
  "total_files": 2,
  "total_size": "1.24 GB",
  "total_size_bytes": 1331439861,
  "files": [
    {
      "fs_id": "81726354129182",
      "filename": "Project_Presentation_4K.mp4",
      "is_dir": 0,
      "size": "1.24 GB",
      "size_bytes": 1331439861,
      "category": "video",
      "direct_download_url": "https://d-hw.baidupcs.com/file/...",
      "dlink": "https://d-hw.baidupcs.com/file/...",
      "fast_stream_url": "/api/terabox/download?url=https%3A%2F%2Fd-hw.baidupcs.com%2Ffile%2F...&filename=Project_Presentation_4K.mp4"
    }
  ]
}
```

---

### 3.10. TikTok Video (Watermark-Free)
**Endpoint**: `GET /api/tiktok?url=<tiktok_url>` or `POST /api/tiktok`

#### Raw Response:
```json
{
  "status": "ok",
  "platform": "tiktok",
  "title": "Funny Dog Video #cute #puppy",
  "author": "doglovers",
  "quality": "HD",
  "duration": 24,
  "thumbnail": "https://p16-sign-va.tiktokcdn.com/tos-maliva-p-0068/...",
  "sourceUrl": "https://www.tiktok.com/@doglovers/video/7106594312292453675",
  "directUrl": "https://v16-webapp-prime.tiktokcdn.com/video/tos/useast2a/...",
  "downloadUrl": "https://xdownderbackend.onrender.com/api/download?url=https%3A%2F%2Fv16-webapp...",
  "engine": "cloud-primary"
}
```

---

### 3.11. Snapchat Spotlight & Public Story
**Endpoint**: `GET /api/snapchat?url=<snapchat_url>` or `POST /api/snapchat`  
**Alias**: `/api/snap`

#### Raw Response:
```json
{
  "status": "ok",
  "platform": "snapchat",
  "title": "Snapchat Spotlight Clip",
  "author": "spotlight_creator",
  "quality": "HD",
  "duration": 12,
  "thumbnail": "https://cf-st.sc-cdn.net/d/...",
  "sourceUrl": "https://www.snapchat.com/spotlight/W7_EDlXWTBiX...",
  "directUrl": "https://cf-st.sc-cdn.net/d/W7_EDlXWTBiX...mp4",
  "downloadUrl": "https://xdownderbackend.onrender.com/api/download?url=https%3A%2F%2Fcf-st...",
  "engine": "cloud-primary"
}
```

---

### 3.12. Twitter / X Video
**Endpoint**: `GET /api/twitter?url=<twitter_url>` or `POST /api/twitter`  
**Alias**: `/api/x`

#### Raw Response:
```json
{
  "status": "success",
  "platform": "twitter",
  "title": "Breaking News Update Video",
  "uploader": "NewsChannel",
  "duration": 45,
  "thumbnail": "https://pbs.twimg.com/media/...",
  "direct_url": "https://video.twimg.com/ext_tw_video/.../vid/avc1/720x1280/video.mp4",
  "formats": [
    {
      "format_id": "http-720",
      "resolution": "720x1280",
      "quality": "720p",
      "url": "https://video.twimg.com/ext_tw_video/.../vid/avc1/720x1280/video.mp4"
    }
  ]
}
```

---

### 3.13. Universal High-Speed Download Streaming Proxy
**Endpoint**: `GET /api/download?url=<target_url>&filename=<desired_name.mp4>`  
Streams the video or audio bytes directly from the CDN to the client browser, forcing a file download dialog (`Content-Disposition: attachment`). Completely eliminates browser CORS restrictions, hotlink blocking, and referrer requirements.

- **Query Parameters**:
  - `url` (*required*): Target video URL or CDN direct URL (MUST be URL-encoded using `encodeURIComponent`).
  - `filename` (*optional*): The desired filename when downloaded (defaults to `media_download.mp4`).
- **Response**: Binary MP4 stream (`Content-Type: video/mp4`).

---

## ⚠️ 4. Error Responses

When an invalid URL or private/restricted post is provided, the API returns a structured JSON error accompanied by the appropriate HTTP status code (`400`, `404`, `500`, or `502`).

### 4.1. Missing URL Parameter (`HTTP 400`)
```json
{
  "status": "error",
  "message": "Missing 'url' parameter"
}
```

### 4.2. Private Post or Extraction Barrier (`HTTP 500` / `502`)
```json
{
  "status": "error",
  "message": "Failed to extract media: Video is private or unavailable."
}
```

---

## 💻 5. Frontend Integration Guide (TypeScript & React)

### 5.1. TypeScript Data Types
Copy and paste this into `types/downloader.ts`:

```typescript
export interface BaseMediaResponse {
  status: "ok" | "success" | "error";
  platform: string;
  title: string;
  author?: string;
  uploader?: string;
  quality?: string;
  thumbnail?: string;
  thumbnail_url?: string;
  duration?: number | null;
  directUrl?: string;
  downloadUrl?: string;
  primary_stream_url?: string;
  sourceUrl?: string;
  engine?: string;
  message?: string;
}

export interface YouTubeFormat {
  format_id: string;
  format_note: string;
  ext: string;
  quality: string;
  resolution: string;
  fps?: number;
  filesize?: string;
  filesize_bytes?: number;
  bitrate_kbps?: number;
  has_video: boolean;
  has_audio: boolean;
  url: string;
}

export interface YouTubeMediaResponse {
  status: "success" | "error";
  platform: "youtube";
  mode: string;
  title: string;
  uploader: string;
  duration_seconds: number;
  thumbnail_url: string;
  available_resolutions: string[];
  primary_stream_url: string;
  primary_audio_url?: string;
  total_video_qualities: number;
  total_audio_streams: number;
  video_formats: YouTubeFormat[];
  audio_formats: YouTubeFormat[];
  message?: string;
}

export interface SpotifyTrack {
  title: string;
  artist: string;
  album: string;
  duration_seconds: number;
  cover: string;
  spotify_url: string;
  download_url: string;
}

export interface SpotifyMediaResponse {
  status: "success" | "error";
  platform: "spotify";
  url: string;
  total_tracks: number;
  tracks: SpotifyTrack[];
  message?: string;
}

export interface TeraBoxFile {
  fs_id: string;
  filename: string;
  size: string;
  size_bytes: number;
  category: string;
  direct_download_url: string;
  dlink: string;
  fast_stream_url: string;
}

export interface TeraBoxMediaResponse {
  status: "success" | "error";
  platform: "terabox";
  title: string;
  total_files: number;
  total_size: string;
  files: TeraBoxFile[];
  message?: string;
}
```

### 5.2. React / Next.js Hook (`useDownloader.ts`)
```typescript
import { useState } from "react";

const API_BASE = "https://xdownderbackend.onrender.com";

export function useDownloader() {
  const [loading, setLoading] = useState<boolean>(false);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const extractMedia = async (targetUrl: string) => {
    setLoading(true);
    setError(null);
    setData(null);

    try {
      const response = await fetch(`${API_BASE}/api/general`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: targetUrl.trim() }),
      });

      const json = await response.json();
      if (!response.ok || json.status === "error") {
        throw new Error(json.message || "Failed to extract media.");
      }

      setData(json);
      return json;
    } catch (err: any) {
      const message = err.message || "Something went wrong while connecting to the server.";
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const getProxyDownloadUrl = (directUrl: string, filename?: string) => {
    const name = encodeURIComponent(filename || "media_download.mp4");
    return `${API_BASE}/api/download?url=${encodeURIComponent(directUrl)}&filename=${name}`;
  };

  return { extractMedia, data, loading, error, getProxyDownloadUrl };
}
```

### 5.3. One-Click Download Trigger (Frontend Helper)
```javascript
export function triggerBrowserDownload(downloadUrl, filename = "video.mp4") {
  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.setAttribute("download", filename);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}
```
