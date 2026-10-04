# ⚡ OmniDownloader Backend API (Render-Ready)

Single-file production backend (`main.py`) providing high-speed media extraction endpoints for **Instagram, Spotify, Apple Music, TeraBox, YouTube, TikTok, Snapchat, Twitter/X**, and a **General / Universal** endpoint that auto-detects links.

---

## 🚀 Quick Start (Local Run)

```bash
cd backend
pip install -r requirements.txt
python main.py
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser or make a request to see the live JSON API Directory.

---

## 🌐 Deploy to Render (Step-by-Step)

Render is 100% supported out-of-the-box!

### Option 1: Automatic via Blueprint (`render.yaml`)
1. Push this `backend` repo/folder to GitHub.
2. Go to **[Render Dashboard](https://dashboard.render.com/)** -> **New** -> **Blueprint**.
3. Select your repository. Render will automatically read `render.yaml` and configure everything!

### Option 2: Manual Web Service
1. In Render, click **New +** -> **Web Service**.
2. Connect your GitHub repository.
3. Configure the settings:
   - **Root Directory**: `backend` (if located inside a subfolder) or leave empty if `main.py` is at root.
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT main:app`
   - **Health Check Path**: `/health`
4. **Environment Variables** (Optional, under Environment tab):
   - `NDUS`: `YuLuQdPpeHuiMGEQDXpWDu6K2P4-xInj8YGEzswD`
   - `COOKIES_DATA`: *(Paste raw Netscape or JSON cookies text from Cookie-Editor here for Instagram/TeraBox login)*.

---

## 📡 API Endpoints Reference

All endpoints support both **GET** (with `?url=...`) and **POST** (with JSON `{ "url": "..." }`).

| Service | Endpoint | Description |
|---|---|---|
| **Universal / General** | `/api/general` or `/api/universal` | Auto-detects platform and resolves media links |
| **Instagram** | `/api/instagram` | Reels, Posts, Carousels, Stories, Highlights, Profiles |
| **Instagram Sub-routes** | `/api/instagram/post`, `/api/instagram/story`, `/api/instagram/highlight`, `/api/instagram/profile` | Direct targeted Instagram extraction |
| **Spotify** | `/api/spotify` | Single Tracks, Albums, Playlists (Direct 320kbps MP3s) |
| **Apple Music** | `/api/apple` or `/api/apple-music` | Apple Music Songs, Albums, Playlists (Direct MP3) |
| **TeraBox** | `/api/terabox` | File & Folder tree, direct download link, sizes |
| **TeraBox Proxy** | `/api/terabox/download` | High-speed streaming proxy bypass download |
| **YouTube** | `/api/youtube` or `/api/yt` | Videos, Shorts, Playlists, YT Music (`&audio=true` for MP3) |
| **TikTok** | `/api/tiktok` | Watermark-free video & audio |
| **Snapchat** | `/api/snapchat` | Spotlight clips & stories |
| **Twitter / X** | `/api/twitter` or `/api/x` | Videos, clips & media |
| **Health Check** | `/health` | Render uptime monitoring (HTTP 200 OK) |
| **API Directory** | `/api/services` | JSON schema of all endpoints |

---

## 🧪 Example API Calls

### 1. General Auto-Detector
```bash
curl "http://localhost:5000/api/general?url=https://www.instagram.com/reel/DCXYZ123/"
```

### 2. Spotify MP3 Direct Link
```bash
curl "http://localhost:5000/api/spotify?url=https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
```

### 3. Apple Music MP3 Direct Link
```bash
curl "http://localhost:5000/api/apple?url=https://music.apple.com/us/album/song-name/123456?i=78910"
```

### 4. TeraBox File & Fast Download Link
```bash
curl "http://localhost:5000/api/terabox?url=https://1024tera.com/s/1abcdef"
```

### 5. YouTube Video & Audio
```bash
curl "http://localhost:5000/api/youtube?url=https://youtu.be/dQw4w9WgXcQ"
# For audio only:
curl "http://localhost:5000/api/youtube?url=https://youtu.be/dQw4w9WgXcQ&audio=true"
```

---

## 🍪 Handling Cookies on Render

On Render (ephemeral hosting), you don't need to commit your private `cookies.txt` to GitHub!
Simply set an **Environment Variable** in your Render Dashboard:
- Key: `COOKIES_DATA`
- Value: *Paste entire content of your cookies file or JSON export*

The backend will automatically detect `COOKIES_DATA`, load the session, and authenticate requests for Instagram and TeraBox.
