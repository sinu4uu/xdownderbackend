

import os
import sys
import re
import time
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, quote, unquote

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
import yt_dlp
import instaloader
from instaloader import Instaloader, Profile, Post

try:
    from pytubefix import YouTube as PyTubeYouTube
except ImportError:
    PyTubeYouTube = None

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

# ==============================================================================
# HIGH-SPEED CONNECTION POOLING & IN-MEMORY TTL CACHE
# ==============================================================================
def create_pooled_session(pool_size: int = 50) -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=1)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s

SHARED_SESSION = create_pooled_session()

# In-Memory Cache (TTL: 5 minutes)
CACHE_STORE: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 300

def get_cached_media(key: str) -> Optional[Any]:
    now = time.time()
    if key in CACHE_STORE:
        exp, data = CACHE_STORE[key]
        if now < exp:
            if isinstance(data, dict):
                res = dict(data)
                res["cached"] = True
                return res
            return data
        else:
            del CACHE_STORE[key]
    return None

def set_cached_media(key: str, data: Any, ttl: int = CACHE_TTL):
    if len(CACHE_STORE) > 1000:
        now = time.time()
        for k in list(CACHE_STORE.keys())[:200]:
            if now >= CACHE_STORE[k][0]:
                del CACHE_STORE[k]
    CACHE_STORE[key] = (time.time() + ttl, data)

# ==============================================================================
# 1. CONFIGURATION & ENVIRONMENT (RENDER-FRIENDLY)
# ==============================================================================
PORT = int(os.environ.get("PORT", 5000))
HOST = os.environ.get("HOST", "0.0.0.0")
APP_NAME = "XDOWNDERBACKEND"
APP_VERSION = "7.0.0-XDOWNDERBACKEND"
DEFAULT_NDUS = os.environ.get("NDUS", "YuLuQdPpeHuiMGEQDXpWDu6K2P4-xInj8YGEzswD")
TERABOX_API_ENDPOINT = os.environ.get("TERABOX_API_ENDPOINT", "https://terabox-dl-pink.vercel.app/api")

# Handle Cookies File & Render Environment Variable
BASE_DIR = Path(__file__).resolve().parent
COOKIES_FILE = os.environ.get("COOKIES_FILE", str(BASE_DIR / "cookies.txt"))
if not os.path.exists(COOKIES_FILE):
    parent_cookies = BASE_DIR.parent / "cookies.txt"
    if parent_cookies.exists():
        COOKIES_FILE = str(parent_cookies)

# Render auto-write cookies from env variable
ENV_COOKIES = os.environ.get("COOKIES_DATA") or os.environ.get("COOKIES_TXT")
if ENV_COOKIES and (not os.path.exists(COOKIES_FILE) or os.path.getsize(COOKIES_FILE) == 0):
    try:
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(ENV_COOKIES.strip())
    except Exception:
        pass


# ==============================================================================
# 2. UTILITY & HELPER FUNCTIONS
# ==============================================================================
def sanitize_filename(filename: str) -> str:
    """Sanitizes strings for safe filesystem and HTTP header filenames."""
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    filename = filename.replace("\n", " ").replace("\r", " ").strip()
    return filename[:150] if filename else "media_file"


def format_bytes(bytes_num: Union[int, str, float], decimals: int = 2) -> str:
    """Formats raw bytes into human-readable text (KB, MB, GB)."""
    try:
        n = float(bytes_num)
    except (ValueError, TypeError):
        return "0 B"

    if n <= 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while n >= 1024.0 and i < len(units) - 1:
        n /= 1024.0
        i += 1

    return f"{n:.{decimals}f} {units[i]}"


def parse_cookies_content(content: str) -> Dict[str, str]:
    """Parses cookies from JSON, Netscape, or key=value string formats."""
    if not content:
        return {}

    content = content.strip()
    # 1. JSON
    if content.startswith("[") or content.startswith("{"):
        try:
            data = json.loads(content)
            cookies_dict = {}
            if isinstance(data, list):
                for item in data:
                    name = item.get("name")
                    val = item.get("value")
                    if name and val is not None:
                        cookies_dict[name] = str(val)
            elif isinstance(data, dict):
                cookies_dict = {str(k): str(v) for k, v in data.items()}
            if cookies_dict:
                return cookies_dict
        except Exception:
            pass

    # 2. Netscape / Key=Value lines
    cookies_dict = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) >= 7:
            cookies_dict[parts[5].strip()] = parts[6].strip()
        elif "=" in line:
            for sub in line.split(";"):
                if "=" in sub:
                    k, v = sub.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k:
                        cookies_dict[k] = v

    return cookies_dict


def parse_cookies_file(filepath: str) -> Dict[str, str]:
    """Reads and parses cookies from disk."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return parse_cookies_content(f.read())
    except Exception:
        return {}


def load_effective_cookies(
    cookie_src: Optional[Union[str, dict]] = None,
    default_path: str = COOKIES_FILE
) -> Dict[str, str]:
    """Resolves cookies from request parameters, environment variables, or disk."""
    if isinstance(cookie_src, dict):
        return {str(k): str(v) for k, v in cookie_src.items()}

    if isinstance(cookie_src, str) and cookie_src.strip():
        candidate = cookie_src.strip()
        if os.path.isfile(candidate):
            parsed = parse_cookies_file(candidate)
            if parsed:
                return parsed
        parsed = parse_cookies_content(candidate)
        if parsed:
            return parsed

    # Check env variables
    env_content = os.environ.get("COOKIES_DATA") or os.environ.get("COOKIES_TXT") or os.environ.get("TERABOX_COOKIES")
    if env_content:
        parsed = parse_cookies_content(env_content)
        if parsed:
            return parsed

    # Check file path
    if os.path.exists(default_path):
        parsed = parse_cookies_file(default_path)
        if parsed:
            return parsed

    # Fallback to NDUS
    ndus = os.environ.get("NDUS") or DEFAULT_NDUS
    if ndus:
        return {"ndus": ndus.strip()}

    return {}


# ==============================================================================
# 3. SPOTIFY SERVICE (reCAPTCHA v3 + Spotidown MP3 Resolver)
# ==============================================================================
SPOTI_BASE = "https://spotidown.app"
SPOTI_SITEKEY = "6Ld_2e4pAAAAAD5s_qQ-sL6oZ6v3wXfW7bS-1J1m"
SPOTI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/134.0.0.0 Safari/537.36"
)

_RECAPTCHA_V_CACHE = {"v": "xds0flIqqjcDFFcwjpOC62Kc", "exp": 0.0}

def get_recaptcha_v3_token(site_key: str = SPOTI_SITEKEY, page_url: str = f"{SPOTI_BASE}/en2") -> Optional[str]:
    """Generates an invisible reCAPTCHA v3 response token in pure Python with engine cache."""
    try:
        domain_match = re.search(r"https?://([^/]+)", page_url)
        domain = domain_match.group(1) if domain_match else "spotidown.app"
        co = base64.b64encode(f"https://{domain}:443".encode()).decode().rstrip("=") + "."
        s = SHARED_SESSION

        now = time.time()
        if now > _RECAPTCHA_V_CACHE["exp"]:
            try:
                r_api = s.get(f"https://www.google.com/recaptcha/api.js?render={site_key}", timeout=5)
                v_match = re.search(r"releases/([^/]+)/recaptcha", r_api.text)
                if v_match:
                    _RECAPTCHA_V_CACHE["v"] = v_match.group(1)
                    _RECAPTCHA_V_CACHE["exp"] = now + 3600
            except Exception:
                pass
        v = _RECAPTCHA_V_CACHE["v"]

        anchor_url = f"https://www.google.com/recaptcha/api2/anchor?ar=1&k={site_key}&co={co}&hl=en&v={v}&size=invisible&cb=123"
        r_anchor = s.get(anchor_url, timeout=6)
        m = re.search(r'id="recaptcha-token"\s+value="([^"]+)"', r_anchor.text)
        if not m:
            return None
        token = m.group(1)

        reload_url = f"https://www.google.com/recaptcha/api2/reload?k={site_key}"
        payload = {
            "v": v,
            "reason": "q",
            "c": token,
            "k": site_key,
            "co": co,
            "hl": "en",
            "size": "invisible",
        }
        r_reload = s.post(reload_url, data=payload, timeout=6)
        m2 = re.search(r'"rresp","([^"]+)"', r_reload.text)
        return m2.group(1) if m2 else None
    except Exception:
        return None


def fetch_spotify_tracks(spotify_url: str, max_workers: int = 10) -> Dict[str, Any]:
    """Fetches high-quality direct MP3 stream links for Spotify tracks/albums/playlists."""
    token = get_recaptcha_v3_token(SPOTI_SITEKEY, f"{SPOTI_BASE}/en2") or "faketoken"
    s = SHARED_SESSION
    headers = {
        "User-Agent": SPOTI_UA,
        "Referer": f"{SPOTI_BASE}/en2",
        "Origin": SPOTI_BASE,
        "X-Requested-With": "XMLHttpRequest",
    }

    r = s.post(f"{SPOTI_BASE}/action", data={
        "url": spotify_url,
        "g-recaptcha-response": token,
    }, headers=headers, timeout=20)
    r.raise_for_status()

    try:
        resp = r.json()
    except ValueError:
        raise RuntimeError("Invalid response from Spotify scraper backend.")

    if resp.get("error"):
        raise RuntimeError(resp.get("message", "Spotify scraper returned an error."))

    html = resp.get("data", "")
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.find_all("form", {"name": "submitspurl"})
    if not forms:
        raise RuntimeError("No tracks found at the provided Spotify URL.")

    img = soup.find("img")
    fallback_thumb = img["src"] if img else None

    track_forms = []
    for form in forms:
        fields = {}
        for inp in form.find_all("input"):
            if inp.get("name"):
                fields[inp["name"]] = inp.get("value", "")
        track_forms.append(fields)

    def _resolve_one(form_data: dict, index: int) -> dict:
        try:
            raw_b64 = form_data.get("data", "")
            info = json.loads(base64.b64decode(raw_b64).decode()) if raw_b64 else {}
            title = info.get("name", f"Track {index + 1}")
            artist = info.get("artist", "")
            name = f"{title} - {artist}" if artist else title
            thumb = info.get("cover") or info.get("image") or info.get("thumb") or fallback_thumb
        except Exception:
            title, artist, name, thumb = f"Track {index + 1}", "", f"Track {index + 1}", fallback_thumb

        dl_url = None
        err = None
        try:
            r_track = s.post(f"{SPOTI_BASE}/action/track", data=form_data, timeout=30)
            if r_track.status_code == 200:
                t_resp = r_track.json()
                if not t_resp.get("error"):
                    t_soup = BeautifulSoup(t_resp.get("data", ""), "html.parser")
                    a = t_soup.find("a", href=re.compile(r"/dl\?token=|rapid\.spotidown"))
                    if a:
                        dl_url = a["href"]
                        if dl_url.startswith("/"):
                            dl_url = SPOTI_BASE + dl_url
                    else:
                        for a_tag in t_soup.find_all("a", href=re.compile(r"https?://")):
                            dl_url = a_tag["href"]
                            break
                else:
                    err = t_resp.get("message")
        except Exception as ex:
            err = str(ex)

        return {
            "index": index + 1,
            "title": title,
            "artist": artist,
            "full_name": name,
            "thumbnail_url": thumb,
            "download_url": dl_url,
            "error": err if not dl_url else None
        }

    resolved = [None] * len(track_forms)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_resolve_one, form, idx): idx for idx, form in enumerate(track_forms)}
        for future in as_completed(futures):
            idx = futures[future]
            resolved[idx] = future.result()

    return {
        "status": "success",
        "platform": "spotify",
        "url": spotify_url,
        "total_tracks": len(resolved),
        "tracks": resolved,
    }


# ==============================================================================
# 4. APPLE MUSIC SERVICE (aplmate.com Engine)
# ==============================================================================
APL_BASE = "https://aplmate.com"
APL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": APL_BASE,
    "Referer": f"{APL_BASE}/",
    "X-Requested-With": "XMLHttpRequest",
}

def fetch_apple_music_tracks(apple_url: str, max_workers: int = 10) -> Dict[str, Any]:
    """Fetches high-quality direct MP3 download URLs from Apple Music links."""
    s = SHARED_SESSION
    s.headers.update(APL_HEADERS)

    r_ver = s.post(f"{APL_BASE}/action/userverify", data={"url": apple_url}, timeout=20)
    r_ver.raise_for_status()
    try:
        resp_ver = r_ver.json()
    except ValueError:
        raise RuntimeError("Invalid response from Apple Music verification backend.")

    token = resp_ver.get("token")
    if not resp_ver.get("success") or not token:
        raise RuntimeError(resp_ver.get("message", "User verification failed on Apple Music backend."))

    r_act = s.post(
        f"{APL_BASE}/action",
        data={"url": apple_url, "cf-turnstile-response": token},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=25,
    )
    r_act.raise_for_status()
    try:
        resp_act = r_act.json()
    except ValueError:
        raise RuntimeError("Invalid response format from Apple Music action endpoint.")

    if resp_act.get("error"):
        raise RuntimeError(resp_act.get("message", "Failed to fetch Apple Music data."))

    html = resp_act.get("data", "") or resp_act.get("html", "")
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.find_all("form", {"name": "submitapurl"})

    fallback_thumb = None
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "mzstatic.com" in src or "mzcdn.com" in src:
            fallback_thumb = src
            break

    if not forms:
        raise RuntimeError("No tracks found at the provided Apple Music URL.")

    track_forms = []
    for form in forms:
        fields = {}
        for inp in form.find_all("input"):
            if inp.get("name"):
                fields[inp["name"]] = inp.get("value", "")
        track_forms.append(fields)

    def _resolve_one(form_data: dict, index: int) -> dict:
        try:
            raw_b64 = form_data.get("data", "")
            info = json.loads(base64.b64decode(raw_b64).decode()) if raw_b64 else {}
            title = info.get("name", f"Track {index + 1}")
            artist = info.get("artist", "")
            name = f"{title} - {artist}" if artist else title
            thumb = info.get("cover") or info.get("image") or fallback_thumb
        except Exception:
            title, artist, name, thumb = f"Track {index + 1}", "", f"Track {index + 1}", fallback_thumb

        dl_url = None
        err = None
        try:
            r_track = s.post(f"{APL_BASE}/action/track", data=form_data, timeout=30)
            if r_track.status_code == 200:
                t_resp = r_track.json()
                if not t_resp.get("error"):
                    t_html = t_resp.get("data", "") or t_resp.get("html", "")
                    t_soup = BeautifulSoup(t_html, "html.parser")
                    for a in t_soup.find_all("a", href=re.compile(r"cdndl\.aplmate\.com|/mp3\?token=")):
                        dl_url = a["href"]
                        if dl_url.startswith("/"):
                            dl_url = APL_BASE + dl_url
                        break
                    if not dl_url:
                        for a in t_soup.find_all("a", href=re.compile(r"https?://")):
                            if "ko-fi" not in a["href"] and "buymeacoffee" not in a["href"]:
                                dl_url = a["href"]
                                break
                else:
                    err = t_resp.get("message")
        except Exception as ex:
            err = str(ex)

        return {
            "index": index + 1,
            "title": title,
            "artist": artist,
            "full_name": name,
            "thumbnail_url": thumb,
            "download_url": dl_url,
            "error": err if not dl_url else None
        }

    resolved = [None] * len(track_forms)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_resolve_one, form, idx): idx for idx, form in enumerate(track_forms)}
        for future in as_completed(futures):
            idx = futures[future]
            resolved[idx] = future.result()

    return {
        "status": "success",
        "platform": "apple_music",
        "url": apple_url,
        "total_tracks": len(resolved),
        "tracks": resolved,
    }


# ==============================================================================
# 5. TERABOX SERVICE (Direct URLs, Folder Recurse, Streaming Proxy)
# ==============================================================================
def extract_surl(url_or_surl: str) -> Tuple[str, str]:
    s = unquote(str(url_or_surl or "").strip())
    param_match = re.search(r"[?&]surl=([a-zA-Z0-9_-]+)", s)
    if param_match:
        key = param_match.group(1)
    else:
        path_match = re.search(r"/(?:s|share|filelist)/([a-zA-Z0-9_-]+)", s)
        if path_match:
            key = path_match.group(1)
        else:
            key = s

    key = re.sub(r"[^a-zA-Z0-9_-]", "", key)
    if key.startswith("1") and len(key) > 1:
        short_url = key[1:]
        surl_param = key
    else:
        short_url = key
        surl_param = "1" + key

    return surl_param, short_url


def extract_jstoken(html_text: str) -> Optional[str]:
    patterns = [
        r'fn%28%22(.*?)%22%29',
        r'fn\("([^"]+)"\)',
        r'jsToken\s*=\s*["\']([^"\']+)["\']',
        r'jsToken["\']?\s*:\s*["\']([^"\']+)["\']',
        r'window\.jsToken\s*=\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text)
        if match and match.group(1):
            return match.group(1)
    return None


def parse_dlink_params(dlink: str) -> Tuple[str, str]:
    expires = "8h"
    region = "jp"
    if dlink:
        try:
            parsed = urlparse(dlink)
            qs = parse_qs(parsed.query)
            if "expires" in qs and qs["expires"]:
                expires = qs["expires"][0]
            if "region" in qs and qs["region"]:
                region = qs["region"][0]
        except Exception:
            pass
    return expires, region


def get_terabox_file_type(category: Union[int, str], duration: Optional[int] = None) -> str:
    cat = str(category or "").strip()
    if cat == "1" or duration is not None:
        return "video"
    elif cat == "2":
        return "audio"
    elif cat == "3":
        return "image"
    elif cat == "4":
        return "document"
    elif cat == "5":
        return "archive"
    return "file"


def build_terabox_response(url: str, parsed_result: dict) -> dict:
    raw_list = parsed_result.get("list", [])
    if not raw_list:
        raise RuntimeError("No files found in the provided TeraBox link")

    is_folder = bool(parsed_result.get("is_folder", False))
    formatted_files = []

    for item in raw_list:
        sz_bytes = 0
        try:
            if "size" in item and item["size"] is not None:
                sz_bytes = int(item["size"])
        except (ValueError, TypeError):
            sz_bytes = 0

        dlink = item.get("dlink") or ""
        expires, region = parse_dlink_params(dlink)
        thumbs_raw = item.get("thumbs") or {}

        file_duration = item.get("duration")
        if file_duration is not None:
            try:
                file_duration = int(file_duration)
            except (ValueError, TypeError):
                pass

        width = item.get("width")
        height = item.get("height")
        resolution = None
        if width is not None and height is not None:
            try:
                resolution = {"width": int(width), "height": int(height)}
            except (ValueError, TypeError):
                resolution = {"width": width, "height": height}

        file_name = item.get("server_filename") or ""
        proxy_dl = f"/api/terabox/download?url={quote(dlink)}&filename={quote(file_name)}" if dlink else ""

        formatted_files.append({
            "adult_content": bool(item.get("is_adult") == 1 or item.get("is_adult") is True),
            "download": {
                "direct_url": dlink,
                "proxy_download_url": proxy_dl,
                "expires": expires,
                "region": region,
            },
            "duration": file_duration,
            "fs_id": str(item.get("fs_id")) if item.get("fs_id") is not None else None,
            "md5": item.get("md5"),
            "name": file_name,
            "path": item.get("path") or "",
            "resolution": resolution,
            "size": {
                "bytes": sz_bytes,
                "text": format_bytes(sz_bytes),
            },
            "thumbnails": {
                "icon": thumbs_raw.get("icon"),
                "large": thumbs_raw.get("url3"),
                "medium": thumbs_raw.get("url2"),
                "small": thumbs_raw.get("url1"),
            },
            "type": get_terabox_file_type(item.get("category"), file_duration),
        })

    first_file = formatted_files[0]
    raw_title = parsed_result.get("title") or first_file["name"] or ""
    clean_title = raw_title.lstrip("/") if isinstance(raw_title, str) else str(raw_title)
    total_size_bytes = sum(f["size"]["bytes"] for f in formatted_files)

    return {
        "status": "success",
        "platform": "terabox",
        "download": first_file["download"],
        "file": {
            "duration": first_file["duration"],
            "fs_id": first_file["fs_id"],
            "md5": first_file["md5"],
            "name": first_file["name"],
            "path": first_file["path"],
            "resolution": first_file["resolution"],
            "size": first_file["size"],
            "type": first_file["type"],
        },
        "files": formatted_files,
        "is_folder": is_folder,
        "message": "Folder fetched successfully" if is_folder else "File fetched successfully",
        "meta": {
            "request_id": parsed_result.get("request_id"),
            "server_time": parsed_result.get("server_time") or int(time.time()),
        },
        "share": {
            "share_id": parsed_result.get("share_id"),
            "title": clean_title if clean_title else first_file["name"],
            "uk": parsed_result.get("uk"),
            "url": url,
        },
        "thumbnails": first_file["thumbnails"],
        "total_files": len(formatted_files),
        "total_size": {
            "bytes": total_size_bytes,
            "text": format_bytes(total_size_bytes),
        },
    }


def fetch_terabox_details(
    surl_or_url: str,
    cookies_input: Optional[Union[str, dict]] = None
) -> Dict[str, Any]:
    """Fetches full file/folder metadata, tree structure, and fast direct download links from TeraBox."""
    clean_url = unquote(str(surl_or_url or "").strip())

    # 1. Primary API Endpoint
    try:
        req_params = {"url": clean_url, "key": "7354"}
        if cookies_input:
            req_params["cookies"] = json.dumps(cookies_input) if isinstance(cookies_input, (dict, list)) else str(cookies_input)

        r_api = requests.get(TERABOX_API_ENDPOINT, params=req_params, timeout=12)
        if r_api.status_code == 200:
            res_json = r_api.json()
            if res_json.get("status") == "success" and res_json.get("download", {}).get("direct_url"):
                return res_json
    except Exception:
        pass

    # 2. Local Fallback Crawler
    surl_param, short_url = extract_surl(clean_url)
    cookies = load_effective_cookies(cookies_input)
    if "ndus" not in cookies and DEFAULT_NDUS:
        cookies["ndus"] = DEFAULT_NDUS

    if curl_requests:
        session = curl_requests.Session(impersonate="chrome110")
    else:
        session = requests.Session()

    session.cookies.update(cookies)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.terabox.app/",
    }

    domains = ["https://dm.terabox.app", "https://www.terabox.app", "https://www.1024tera.com", "https://www.terabox.com"]
    jsToken = None
    for dom in domains:
        try:
            resp = session.get(f"{dom}/sharing/link?surl={surl_param}", headers=headers, timeout=10)
            if resp.status_code == 200:
                jsToken = extract_jstoken(resp.text)
                if jsToken:
                    break
        except Exception:
            pass

    if not jsToken:
        raise RuntimeError("Failed to extract jsToken from TeraBox. Valid NDUS cookie required.")

    api_url = "https://dm.terabox.app/share/list"
    params = {
        "app_id": "250528",
        "jsToken": jsToken,
        "site_referer": "https://www.terabox.app/",
        "shorturl": short_url,
        "root": "1",
    }
    api_headers = {
        "Host": "dm.terabox.app",
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://dm.terabox.app/sharing/link?surl={short_url}&clearCache=1",
        "Origin": "https://dm.terabox.app",
    }

    api_resp = session.get(api_url, params=params, headers=api_headers, timeout=15)
    try:
        res_data = api_resp.json()
    except Exception:
        raise RuntimeError(f"Invalid JSON from TeraBox API: {api_resp.text[:200]}")

    if res_data.get("errno") != 0:
        params["shorturl"] = surl_param
        try:
            alt_res = session.get(api_url, params=params, headers=api_headers, timeout=15)
            alt_data = alt_res.json()
            if alt_data.get("errno") == 0:
                res_data = alt_data
        except Exception:
            pass

    if res_data.get("errno") != 0:
        raise RuntimeError(res_data.get("errmsg") or f"TeraBox returned error code {res_data.get('errno')}")

    share_id = res_data.get("share_id")
    uk = res_data.get("uk")
    initial_list = res_data.get("list", [])

    all_file_items = []
    folder_queue = []
    has_folder = False

    for item in initial_list:
        if str(item.get("isdir", "0")) == "1":
            has_folder = True
            folder_queue.append(item.get("path"))
        else:
            all_file_items.append(item)

    visited_dirs = set()
    while folder_queue:
        curr_dir = folder_queue.pop(0)
        if curr_dir in visited_dirs:
            continue
        visited_dirs.add(curr_dir)

        dir_params = {
            "app_id": "250528",
            "jsToken": jsToken,
            "site_referer": "https://www.terabox.app/",
            "shorturl": short_url,
            "dir": curr_dir,
        }
        try:
            sub_res = session.get(api_url, params=dir_params, headers=api_headers, timeout=15)
            if sub_res.status_code == 200:
                sub_data = sub_res.json()
                if sub_data.get("errno") == 0 and "list" in sub_data:
                    for sub_item in sub_data["list"]:
                        if str(sub_item.get("isdir", "0")) == "1":
                            folder_queue.append(sub_item.get("path"))
                        else:
                            all_file_items.append(sub_item)
        except Exception:
            pass

    for item in all_file_items:
        if not item.get("dlink") and item.get("fs_id"):
            try:
                dl_params = {
                    "app_id": "250528",
                    "jsToken": jsToken,
                    "shorturl": short_url,
                    "shareid": share_id,
                    "uk": uk,
                    "primaryid": share_id,
                    "product": "share",
                    "nozip": "0",
                    "fid_list": f"[{item.get('fs_id')}]",
                }
                dl_res = session.get("https://dm.terabox.app/share/download", params=dl_params, headers=api_headers, timeout=10)
                if dl_res.status_code == 200:
                    dl_data = dl_res.json()
                    if dl_data.get("errno") == 0 and dl_data.get("dlink"):
                        item["dlink"] = dl_data.get("dlink")
            except Exception:
                pass

    res_data["list"] = all_file_items
    res_data["is_folder"] = has_folder
    res_data["title"] = res_data.get("title") or (all_file_items[0].get("server_filename") if all_file_items else "")

    return build_terabox_response(clean_url, res_data)


# ==============================================================================
# 6. INSTAGRAM SERVICE (Instaloader: Posts, Reels, Carousels, Stories, Highlights)
# ==============================================================================
class InstagramService:
    def __init__(self, cookies_path: str = COOKIES_FILE):
        self.cookies_path = cookies_path
        self.loader = Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
            iphone_support=False,
            sanitize_paths=False,
            request_timeout=25.0,
            max_connection_attempts=2,
        )
        self.setup_auth()

    def setup_auth(self) -> bool:
        cookies = load_effective_cookies(default_path=self.cookies_path)
        if not cookies:
            return False

        session = self.loader.context._session
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "X-IG-App-ID": "936619743392459",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.instagram.com/",
            "Origin": "https://www.instagram.com",
        })

        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".instagram.com")

        csrf = cookies.get("csrftoken")
        if csrf:
            session.headers.update({"X-CSRFToken": csrf})

        user_id = cookies.get("ds_user_id")
        if user_id:
            self.loader.context.username = user_id

        return True

    def extract_post(self, shortcode: str) -> Dict[str, Any]:
        """Extracts direct CDN video/image URLs for a Post or Reel."""
        t0 = time.time()
        try:
            post = Post.from_shortcode(self.loader.context, shortcode)
            elapsed = round(time.time() - t0, 2)

            owner = post.owner_username or "unknown"
            typename = post.typename
            post_type = "reel" if post.is_video else ("carousel" if typename == "GraphSidecar" else "photo")

            media_list = []
            if typename == "GraphSidecar":
                for idx, node in enumerate(post.get_sidecar_nodes(), 1):
                    is_vid = node.is_video
                    media_list.append({
                        "index": idx,
                        "type": "video" if is_vid else "image",
                        "format": "mp4" if is_vid else "jpg",
                        "label": f"Slide {idx} ({'Video' if is_vid else 'Image'})",
                        "url": node.video_url if is_vid else node.display_url,
                    })
            elif post.is_video:
                media_list.append({
                    "index": 1,
                    "type": "video",
                    "format": "mp4",
                    "label": "Full HD Video (.mp4)",
                    "url": post.video_url,
                })
            else:
                media_list.append({
                    "index": 1,
                    "type": "image",
                    "format": "jpg",
                    "label": "High-Res Image (.jpg)",
                    "url": post.url,
                })

            return {
                "status": "success",
                "platform": "instagram",
                "shortcode": shortcode,
                "type": post_type,
                "owner": owner,
                "likes": post.likes,
                "caption": post.caption or "",
                "media_count": len(media_list),
                "media": media_list,
                "extracted_in_seconds": elapsed,
            }
        except Exception as instaloader_err:
            try:
                # Fallback to yt-dlp extractor
                res = extract_ytdlp_media(f"https://www.instagram.com/p/{shortcode}/", cookies_path=self.cookies_path)
                res["platform"] = "instagram"
                res["shortcode"] = shortcode
                return res
            except Exception:
                raise instaloader_err

    def extract_story(self, username: str, story_id: Optional[str] = None) -> Dict[str, Any]:
        """Extracts active story links for a user."""
        t0 = time.time()
        clean_user = username.strip().lstrip("@")
        profile = Profile.from_username(self.loader.context, clean_user)
        stories = list(self.loader.get_stories(userids=[profile.userid]))

        if not stories:
            raise RuntimeError(f"No active stories found for @{profile.username}.")

        items = []
        for s in stories:
            for it in s.get_items():
                items.append(it)

        if not items:
            raise RuntimeError(f"No story media found for @{profile.username}.")

        if story_id:
            matching = [it for it in items if str(it.mediaid) == str(story_id)]
            if matching:
                items = matching

        elapsed = round(time.time() - t0, 2)
        media_list = []
        for idx, it in enumerate(items, 1):
            is_vid = it.is_video
            media_list.append({
                "index": idx,
                "media_id": str(it.mediaid),
                "type": "video" if is_vid else "image",
                "format": "mp4" if is_vid else "jpg",
                "timestamp": it.date_utc.isoformat() + "Z",
                "label": f"Story {idx} ({it.date_local.strftime('%H:%M')})",
                "url": it.video_url if is_vid else it.url,
            })

        return {
            "status": "success",
            "platform": "instagram",
            "type": "story",
            "owner": profile.username,
            "media_count": len(media_list),
            "media": media_list,
            "extracted_in_seconds": elapsed,
        }

    def extract_highlight(self, highlight_id: str) -> Dict[str, Any]:
        """Extracts stories from an Instagram highlight reel."""
        t0 = time.time()
        hl_query = self.loader.context.graphql_query(
            "45246d3fe16ccc6577e0bd297a5db1ab",
            {
                "reel_ids": [],
                "tag_names": [],
                "location_ids": [],
                "highlight_reel_ids": [f"highlight:{highlight_id}"],
                "precomposed_overlay": False,
            },
        )
        reels = hl_query.get("data", {}).get("reels_media", [])
        if not reels:
            raise RuntimeError("Highlight reel not found or expired.")

        reel = reels[0]
        title = reel.get("title", f"highlight_{highlight_id}")
        owner = reel.get("user", {}).get("username", "highlights")
        items_raw = reel.get("items", [])
        elapsed = round(time.time() - t0, 2)

        media_list = []
        for idx, item in enumerate(items_raw, 1):
            is_vid = item.get("is_video", False)
            url = item["video_resources"][0]["src"] if is_vid and item.get("video_resources") else item.get("display_url", "")
            media_list.append({
                "index": idx,
                "type": "video" if is_vid else "image",
                "format": "mp4" if is_vid else "jpg",
                "label": f"Highlight Item {idx}",
                "url": url,
            })

        return {
            "status": "success",
            "platform": "instagram",
            "type": "highlight",
            "highlight_id": highlight_id,
            "title": title,
            "owner": owner,
            "media_count": len(media_list),
            "media": media_list,
            "extracted_in_seconds": elapsed,
        }

    def extract_profile(self, username: str) -> Dict[str, Any]:
        """Extracts Instagram profile details, follower counts, and avatar."""
        t0 = time.time()
        clean_user = username.strip().lstrip("@")
        profile = Profile.from_username(self.loader.context, clean_user)
        elapsed = round(time.time() - t0, 2)

        return {
            "status": "success",
            "platform": "instagram",
            "type": "profile",
            "username": profile.username,
            "full_name": profile.full_name or "",
            "followers": profile.followers,
            "following": profile.followees,
            "total_posts": profile.mediacount,
            "is_verified": profile.is_verified,
            "is_private": profile.is_private,
            "profile_pic_hd_url": profile.profile_pic_url,
            "extracted_in_seconds": elapsed,
        }

    def dispatch_url(self, link: str) -> Dict[str, Any]:
        """Auto-detects Instagram URL type (post, reel, story, highlight, profile)."""
        link = link.strip()
        # Post / Reel
        match_post = re.search(r"(?:/p/|/reel/|/reels/|/tv/)([\w-]+)", link)
        if match_post:
            return self.extract_post(match_post.group(1))

        # Highlight
        match_hl = re.search(r"/stories/highlights/(\d+)", link)
        if match_hl:
            return self.extract_highlight(match_hl.group(1))

        # Story
        match_story = re.search(r"/stories/([^/?#]+)(?:/(\d+))?", link)
        if match_story:
            user = match_story.group(1)
            story_id = match_story.group(2)
            if user.lower() == "highlights" and story_id:
                return self.extract_highlight(story_id)
            return self.extract_story(user, story_id)

        # Profile
        match_profile = re.search(r"(?:instagram\.com/|^@?)([A-Za-z0-9._]+)/?$", link)
        if match_profile:
            user = match_profile.group(1)
            if user.lower() not in ("explore", "direct", "accounts", "reels", "stories", "p"):
                return self.extract_profile(user)

        # Fallback shortcode
        if re.match(r"^[\w-]{8,15}$", link):
            return self.extract_post(link)

        raise ValueError("Could not recognize Instagram link format (post, reel, story, highlight, or profile).")


_IG_SERVICE_SINGLETON: Optional["InstagramService"] = None

def get_instagram_service(cookies_path: str = COOKIES_FILE) -> "InstagramService":
    """Singleton getter for InstagramService to reuse TCP connections and session."""
    global _IG_SERVICE_SINGLETON
    if _IG_SERVICE_SINGLETON is None:
        _IG_SERVICE_SINGLETON = InstagramService(cookies_path=cookies_path)
    return _IG_SERVICE_SINGLETON


# ==============================================================================
# 6.5. PYTUBEFIX YOUTUBE SERVICE (Zero Bot-Detection, No YT-DLP)
# ==============================================================================
WORKING_YT_CLIENTS = ['MWEB', 'WEB', 'WEB_SAFARI']

def get_pytube_instance(url: str):
    """Creates a YouTube instance with client fallback to bypass YouTube's bot detection."""
    if not PyTubeYouTube:
        raise RuntimeError("pytubefix is not installed.")
    last_err = None
    for client_name in WORKING_YT_CLIENTS:
        try:
            yt = PyTubeYouTube(url, client=client_name)
            _ = yt.title
            return yt
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to fetch YouTube media across all clients: {last_err}")


def extract_youtube_pytube(url: str, audio_only: bool = False) -> Dict[str, Any]:
    """Pure pytubefix YouTube extraction without yt-dlp to avoid bot blocks."""
    t0 = time.time()
    yt = get_pytube_instance(url)

    title = yt.title or "YouTube Video"
    uploader = yt.author or "Unknown"
    duration = yt.length
    thumbnail = yt.thumbnail_url

    best_by_quality: Dict[str, Dict[str, Any]] = {}
    audio_by_bitrate: Dict[str, Dict[str, Any]] = {}

    for s in yt.streams:
        itag = str(s.itag)
        ext = s.mime_type.split('/')[-1] if s.mime_type else 'mp4'
        is_prog = s.is_progressive
        has_video = bool(s.includes_video_track)
        has_audio = bool(s.includes_audio_track)
        res = s.resolution
        fps = getattr(s, 'fps', None)
        vcodec = getattr(s, 'video_codec', None)
        acodec = getattr(s, 'audio_codec', None)
        bitrate = getattr(s, 'bitrate', None)
        bitrate_kbps = round(float(bitrate) / 1000, 1) if bitrate else None

        try:
            filesize_bytes = getattr(s, 'filesize_approx', None)
        except Exception:
            filesize_bytes = None

        filesize_text = format_bytes(filesize_bytes) if filesize_bytes else None
        p_tag = res if res else "audio_only"

        fmt_entry = {
            "format_id": itag,
            "format_note": "progressive" if is_prog else ("video only" if has_video else "audio only"),
            "ext": ext,
            "quality": p_tag,
            "resolution": res or "audio only",
            "fps": fps,
            "vcodec": vcodec,
            "acodec": acodec,
            "has_video": has_video,
            "has_audio": has_audio,
            "bitrate_kbps": bitrate_kbps,
            "filesize_bytes": filesize_bytes,
            "filesize": filesize_text,
            "url": getattr(s, "url", None),
        }

        if has_video:
            if p_tag not in best_by_quality:
                best_by_quality[p_tag] = fmt_entry
            else:
                curr = best_by_quality[p_tag]
                if fmt_entry["has_audio"] and not curr["has_audio"]:
                    best_by_quality[p_tag] = fmt_entry
                elif fmt_entry["has_audio"] == curr["has_audio"] and (fmt_entry["bitrate_kbps"] or 0) > (curr.get("bitrate_kbps") or 0):
                    best_by_quality[p_tag] = fmt_entry
        elif has_audio:
            abr_str = getattr(s, 'abr', None) or '128k'
            abr_key = f"{ext}_{abr_str}"
            if abr_key not in audio_by_bitrate:
                audio_by_bitrate[abr_key] = fmt_entry
            elif (fmt_entry["bitrate_kbps"] or 0) > (audio_by_bitrate[abr_key].get("bitrate_kbps") or 0):
                audio_by_bitrate[abr_key] = fmt_entry

    def _parse_h(p_str: str) -> int:
        try:
            return int(p_str.replace("p", ""))
        except Exception:
            return 0

    sorted_video_formats = sorted(best_by_quality.values(), key=lambda x: _parse_h(x["quality"]), reverse=True)
    sorted_audio_formats = sorted(audio_by_bitrate.values(), key=lambda x: (x.get("bitrate_kbps") or 0), reverse=True)
    sorted_video_qualities = {v["quality"]: v for v in sorted_video_formats}

    direct_url = sorted_video_formats[0]["url"] if sorted_video_formats else None
    primary_audio_url = sorted_audio_formats[0]["url"] if sorted_audio_formats else None

    return {
        "status": "success",
        "platform": "youtube",
        "mode": "audio" if audio_only else "all_formats",
        "title": title,
        "uploader": uploader,
        "duration_seconds": duration,
        "format": "m4a" if audio_only else "mp4",
        "available_resolutions": list(sorted_video_qualities.keys()),
        "primary_stream_url": direct_url,
        "primary_audio_url": primary_audio_url,
        "video_streams_by_quality": sorted_video_qualities,
        "video_formats": sorted_video_formats,
        "audio_formats": sorted_audio_formats,
        "total_video_qualities": len(sorted_video_formats),
        "total_audio_streams": len(sorted_audio_formats),
        "thumbnail_url": thumbnail,
        "extracted_in_seconds": round(time.time() - t0, 2),
    }


def download_youtube_pytube(url: str, resolution: str = None, itag: Union[int, str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Downloads YouTube video via pytubefix and returns (file_path, filename, error).
    """
    try:
        yt = get_pytube_instance(url)
        stream = None
        if itag:
            try:
                stream = yt.streams.get_by_itag(int(itag))
            except Exception:
                stream = None

        if not stream and resolution:
            res = resolution.lower() if resolution.lower().endswith("p") else f"{resolution.lower()}p"
            prog = yt.streams.filter(progressive=True, file_extension="mp4")
            stream = prog.filter(resolution=res).first() or yt.streams.filter(file_extension="mp4", res=res).first()

        if not stream:
            prog = yt.streams.filter(progressive=True, file_extension="mp4")
            stream = prog.order_by("resolution").desc().first() or yt.streams.filter(file_extension="mp4").first()

        if not stream:
            return None, None, "No downloadable stream found"

        clean_title = sanitize_filename(yt.title or "youtube_video")
        out_dir = os.path.abspath("./downloads/youtube")
        os.makedirs(out_dir, exist_ok=True)
        res_label = stream.resolution or "stream"
        filename = f"{clean_title}_{res_label}_{stream.itag}.mp4"
        file_path = stream.download(output_path=out_dir, filename=filename)
        return file_path, filename, None
    except Exception as e:
        return None, None, str(e)


# ==============================================================================
# 6.5 PRIMARY CLOUD ENGINE (High-Speed Stealth Extractor)
# ==============================================================================
_CLOUD_BASE = os.environ.get("CLOUD_MEDIA_BASE") or base64.b64decode("aHR0cHM6Ly9yZWVsc2Rvd25sb2FkZXIucHJv").decode("utf-8")
_CLOUD_API = f"{_CLOUD_BASE}/api/download"

def extract_primary_cloud(url: str, timeout: int = 20) -> Optional[Dict[str, Any]]:
    """
    Primary Cloud Engine: high-speed cloud extraction for Facebook, Instagram,
    Snapchat, and TikTok with direct CDN stream resolution and fallback resilience.
    """
    clean_url = (url or "").strip()
    if not clean_url:
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        ),
        "Origin": _CLOUD_BASE,
        "Referer": f"{_CLOUD_BASE}/",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }

    try:
        resp = SHARED_SESSION.post(
            _CLOUD_API,
            json={"url": clean_url},
            headers=headers,
            timeout=timeout
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                dl = data.get("downloadUrl", "")
                if dl and dl.startswith("/"):
                    data["downloadUrl"] = f"{_CLOUD_BASE}{dl}"
                data["engine"] = "cloud-primary"
                return data
    except Exception:
        pass
    return None


def stream_media_url(stream_url: str, chunk_size: int = 65536):
    """Streams video chunks directly from directUrl or proxy stream."""
    actual_url = stream_url
    target_referer = _CLOUD_BASE
    if "api/file" in stream_url and "u=" in stream_url:
        parsed = urlparse(stream_url)
        qs = parse_qs(parsed.query)
        if "u" in qs and qs["u"]:
            actual_url = qs["u"][0]
        if "r" in qs and qs["r"]:
            target_referer = qs["r"][0]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Referer": target_referer,
    }

    resp = SHARED_SESSION.get(actual_url, headers=headers, stream=True, timeout=30)
    if resp.status_code not in (200, 206) and actual_url != stream_url:
        resp = SHARED_SESSION.get(stream_url, headers={"User-Agent": headers["User-Agent"]}, stream=True, timeout=30)

    resp_headers = {
        "Content-Type": resp.headers.get("Content-Type", "video/mp4"),
    }
    if "Content-Length" in resp.headers:
        resp_headers["Content-Length"] = resp.headers["Content-Length"]

    def generate():
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                yield chunk

    return resp.status_code, resp_headers, generate()


# ==============================================================================
# 7. YT-DLP SERVICE (YouTube, Shorts, TikTok, Snapchat, Twitter/X, Generic)
# ==============================================================================
def extract_ytdlp_media(url: str, audio_only: bool = False, cookies_path: str = COOKIES_FILE) -> Dict[str, Any]:
    """Extracts all video and audio formats using yt-dlp across 1000+ sites with complete format tree."""
    t0 = time.time()
    clean_url = (url or "").strip()
    is_youtube = any(y in clean_url.lower() for y in ["youtube.com", "youtu.be"])

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "check_formats": None,
        "socket_timeout": 15,
        "no_color": True,
        "remote_components": ["ejs:github"],
        "js_runtimes": {"node": {}},
    }

    if os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = cookies_path

    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
    except Exception as ex:
        if is_youtube:
            # Fallback 1: Try with android/ios client without cookies
            try:
                retry_opts = dict(ydl_opts)
                retry_opts.pop("cookiefile", None)
                retry_opts["extractor_args"] = {
                    "youtube": {
                        "player_client": ["android", "ios"],
                    }
                }
                with yt_dlp.YoutubeDL(retry_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=False)
            except Exception:
                # Fallback 2: Try with web/ios client
                try:
                    retry_opts2 = dict(ydl_opts)
                    retry_opts2["extractor_args"] = {
                        "youtube": {
                            "player_client": ["ios", "mweb", "web"],
                        }
                    }
                    with yt_dlp.YoutubeDL(retry_opts2) as ydl:
                        info = ydl.extract_info(clean_url, download=False)
                except Exception:
                    raise ex
        else:
            raise ex

    if not info:
        raise RuntimeError("yt-dlp could not extract media info for this URL.")

    elapsed = round(time.time() - t0, 2)
    extractor_name = info.get("extractor", "universal")
    title = info.get("title") or "Untitled"
    uploader = info.get("uploader") or info.get("channel") or info.get("creator") or "Unknown"
    duration = info.get("duration")
    thumbnail = info.get("thumbnail")

    best_by_quality: Dict[str, Dict[str, Any]] = {}
    audio_by_bitrate: Dict[str, Dict[str, Any]] = {}

    for f in info.get("formats", []):
        f_url = f.get("url")
        if not f_url or f.get("ext") in ("mhtml", "jpg", "jpeg", "webp"):
            continue

        format_id = str(f.get("format_id", ""))
        ext = f.get("ext", "")
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        width = f.get("width")
        height = f.get("height")
        fps = f.get("fps")
        format_note = f.get("format_note") or ""
        filesize = f.get("filesize") or f.get("filesize_approx")
        filesize_bytes = int(filesize) if filesize else None
        filesize_text = format_bytes(filesize_bytes) if filesize_bytes else None

        # 100% Accurate has_video & has_audio detection
        has_video = bool(vcodec and str(vcodec).lower() not in ("none", "null", "") and height)
        has_audio = bool(acodec and str(acodec).lower() not in ("none", "null", ""))

        if not has_video and not has_audio:
            continue

        bitrate = f.get("tbr") or f.get("abr") or f.get("vbr")
        bitrate_kbps = round(float(bitrate), 1) if bitrate else None

        p_tag = f"{height}p" if height else "audio_only"
        res_str = f.get("resolution") or (f"{width}x{height}" if width and height else ("audio only" if not has_video else None))

        fmt_entry = {
            "format_id": format_id,
            "format_note": format_note,
            "ext": ext,
            "quality": p_tag,
            "resolution": res_str,
            "width": width,
            "height": height,
            "fps": fps,
            "vcodec": vcodec if has_video else None,
            "acodec": acodec if has_audio else None,
            "has_video": has_video,
            "has_audio": has_audio,
            "bitrate_kbps": bitrate_kbps,
            "filesize_bytes": filesize_bytes,
            "filesize": filesize_text,
            "url": f_url,
        }

        # 1. Clean Deduplication for Video: Exactly ONE best stream per distinct quality/resolution
        if has_video:
            if p_tag not in best_by_quality:
                best_by_quality[p_tag] = fmt_entry
            else:
                curr = best_by_quality[p_tag]
                # Prioritize: has_audio (video+audio combo) > MP4 container > higher bitrate
                if fmt_entry["has_audio"] and not curr["has_audio"]:
                    best_by_quality[p_tag] = fmt_entry
                elif fmt_entry["has_audio"] == curr["has_audio"]:
                    if fmt_entry["ext"] == "mp4" and curr["ext"] != "mp4":
                        best_by_quality[p_tag] = fmt_entry
                    elif fmt_entry["ext"] == curr["ext"] and (fmt_entry.get("bitrate_kbps") or 0) > (curr.get("bitrate_kbps") or 0):
                        best_by_quality[p_tag] = fmt_entry

        # 2. Clean Deduplication for Audio: Distinct bitrates per extension
        elif has_audio and not has_video:
            abr_approx = round(float(f.get("abr") or bitrate or 128))
            a_key = f"{ext}_{abr_approx}k"
            if a_key not in audio_by_bitrate:
                audio_by_bitrate[a_key] = fmt_entry
            else:
                if (fmt_entry.get("bitrate_kbps") or 0) > (audio_by_bitrate[a_key].get("bitrate_kbps") or 0):
                    audio_by_bitrate[a_key] = fmt_entry

    def _parse_height(p_str: str) -> int:
        try:
            return int(p_str.replace("p", ""))
        except Exception:
            return 0

    sorted_video_formats = sorted(best_by_quality.values(), key=lambda x: _parse_height(x["quality"]), reverse=True)
    sorted_audio_formats = sorted(audio_by_bitrate.values(), key=lambda x: (x.get("bitrate_kbps") or 0), reverse=True)
    sorted_video_qualities = {v["quality"]: v for v in sorted_video_formats}

    direct_url = info.get("url")
    if not direct_url and info.get("requested_formats"):
        direct_url = [f.get("url") for f in info["requested_formats"] if f.get("url")]
    elif not direct_url and sorted_video_formats:
        direct_url = sorted_video_formats[0]["url"]

    primary_audio_url = sorted_audio_formats[0]["url"] if sorted_audio_formats else None
    ext = info.get("ext", "mp4" if not audio_only else "m4a")

    return {
        "status": "success",
        "platform": extractor_name.lower(),
        "mode": "audio" if audio_only else "all_formats",
        "title": title,
        "uploader": uploader,
        "duration_seconds": duration,
        "format": ext,
        "available_resolutions": list(sorted_video_qualities.keys()),
        "primary_stream_url": direct_url,
        "primary_audio_url": primary_audio_url,
        "video_streams_by_quality": sorted_video_qualities,
        "video_formats": sorted_video_formats,
        "audio_formats": sorted_audio_formats,
        "total_video_qualities": len(sorted_video_formats),
        "total_audio_streams": len(sorted_audio_formats),
        "thumbnail_url": thumbnail,
        "extracted_in_seconds": elapsed,
    }


# ==============================================================================
# 8. GENERAL / UNIVERSAL ROUTER
# ==============================================================================
def extract_universal(url: str, cookies_path: str = COOKIES_FILE) -> Dict[str, Any]:
    """Smart link analyzer and dispatcher covering all services."""
    link = (url or "").strip()
    if not link:
        raise ValueError("URL cannot be empty.")

    lower = link.lower()

    # 1. Spotify
    if any(d in lower for d in ["open.spotify.com", "spotify.link", "spotify.com"]):
        return fetch_spotify_tracks(link)

    # 2. Apple Music
    if "music.apple.com" in lower:
        return fetch_apple_music_tracks(link)

    # 3. TeraBox
    if any(d in lower for d in [
        "terabox.app", "terabox.com", "1024tera.com", "teraboxlink.com",
        "freeterabox.com", "mirrobox.com", "nephobox.com", "4funbox.com",
        "tibibox.com", "dm.terabox.app"
    ]) or "surl=" in lower:
        return fetch_terabox_details(link)

    # 4. Instagram
    if "instagram.com" in lower or "instagr.am" in lower or re.match(r"^[\w-]{8,15}$", link):
        cloud_data = extract_primary_cloud(link)
        if cloud_data:
            return cloud_data
        ig = InstagramService(cookies_path=cookies_path)
        return ig.dispatch_url(link)

    # 5. Facebook
    if any(d in lower for d in ["facebook.com", "fb.watch", "fb.com", "fb.gg"]):
        cloud_data = extract_primary_cloud(link)
        if cloud_data:
            return cloud_data
        return extract_ytdlp_media(link, cookies_path=cookies_path)

    # 6. YouTube (Handled via PyTubeFix Bot-Bypass, NOT yt-dlp)
    if any(d in lower for d in ["youtube.com", "youtu.be"]):
        return extract_youtube_pytube(link, audio_only=False)

    # 7. TikTok, Snapchat, Twitter, and other supported media
    cloud_data = extract_primary_cloud(link)
    if cloud_data:
        return cloud_data
    return extract_ytdlp_media(link, cookies_path=cookies_path)


# ==============================================================================
# 9. FLASK APPLICATION & REST ENDPOINTS
# ==============================================================================
def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    def get_param(name: str, default: Optional[str] = None) -> Optional[str]:
        """Extracts param from GET query or POST JSON/form."""
        val = request.args.get(name)
        if val is None and request.is_json:
            val = (request.get_json(silent=True) or {}).get(name)
        if val is None and request.form:
            val = request.form.get(name)
        return val if val is not None else default

    # --------------------------------------------------------------------------
    # HEALTH CHECK & DASHBOARD
    # --------------------------------------------------------------------------
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "healthy",
            "version": APP_VERSION,
            "port": PORT,
            "timestamp": int(time.time()),
        }), 200

    @app.route("/", methods=["GET"])
    def home():
        return jsonify({
            "service": "XDOWNDERBACKEND Universal API",
            "version": APP_VERSION,
            "status": "online",
            "message": "Welcome to XDOWNDERBACKEND API. Use /api/general?url={url} for universal extraction or service-specific endpoints.",
            "endpoints": {
                "universal": "/api/general?url={media_url}",
                "instagram": "/api/instagram?url={post_or_reel_url}",
                "facebook": "/api/facebook?url={facebook_video_url}",
                "spotify": "/api/spotify?url={track_or_album_url}",
                "apple_music": "/api/apple?url={apple_music_url}",
                "terabox": "/api/terabox?url={terabox_url}",
                "youtube": "/api/youtube?url={video_or_shorts_url}",
                "tiktok": "/api/tiktok?url={tiktok_url}",
                "snapchat": "/api/snapchat?url={snapchat_url}",
                "twitter_x": "/api/twitter?url={tweet_or_x_url}",
                "health": "/health",
                "services": "/api/services"
            }
        }), 200

    @app.route("/api/services", methods=["GET"])
    def list_services():
        """Lists all supported services and documentation."""
        return jsonify({
            "service": "XDOWNDERBACKEND Universal API",
            "version": APP_VERSION,
            "status": "online",
            "endpoints": {
                "universal": {
                    "path": "/api/general",
                    "aliases": ["/api/universal"],
                    "methods": ["GET", "POST"],
                    "description": "Auto-detects platform (Spotify, IG, FB, TeraBox, Apple, YouTube, etc.) and returns structured media JSON"
                },
                "instagram": {
                    "path": "/api/instagram",
                    "sub_endpoints": [
                        "/api/instagram/post",
                        "/api/instagram/story",
                        "/api/instagram/highlight",
                        "/api/instagram/profile"
                    ],
                    "methods": ["GET", "POST"],
                    "description": "Extracts Instagram reels, posts, carousels, stories, highlights, and profiles"
                },
                "facebook": {
                    "path": "/api/facebook",
                    "aliases": ["/api/fb"],
                    "methods": ["GET", "POST"],
                    "description": "Extracts Facebook videos, reels, and stories in high resolution"
                },
                "spotify": {
                    "path": "/api/spotify",
                    "methods": ["GET", "POST"],
                    "description": "Extracts Spotify tracks, albums, playlists with direct 320kbps MP3 download links"
                },
                "apple_music": {
                    "path": "/api/apple",
                    "aliases": ["/api/apple-music"],
                    "methods": ["GET", "POST"],
                    "description": "Extracts Apple Music songs, albums, and playlists with direct MP3 streams"
                },
                "terabox": {
                    "path": "/api/terabox",
                    "methods": ["GET", "POST"],
                    "description": "Extracts TeraBox files and folders with direct download link and sizes"
                },
                "youtube": {
                    "path": "/api/youtube",
                    "aliases": ["/api/yt"],
                    "methods": ["GET", "POST"],
                    "description": "Extracts YouTube videos, shorts, resolutions, and native audio (.m4a/.mp3)"
                },
                "tiktok": {
                    "path": "/api/tiktok",
                    "methods": ["GET", "POST"],
                    "description": "Extracts watermark-free TikTok videos and audio streams"
                },
                "snapchat": {
                    "path": "/api/snapchat",
                    "methods": ["GET", "POST"],
                    "description": "Extracts Snapchat spotlight clips and stories"
                },
                "twitter": {
                    "path": "/api/twitter",
                    "aliases": ["/api/x"],
                    "methods": ["GET", "POST"],
                    "description": "Extracts Twitter / X videos and clips"
                }
            }
        })

    # --------------------------------------------------------------------------
    # 1. GENERAL / UNIVERSAL ENDPOINT
    # --------------------------------------------------------------------------
    @app.route("/api/general", methods=["GET", "POST"])
    @app.route("/api/universal", methods=["GET", "POST"])
    def api_general():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing required 'url' parameter"}), 400
        cache_key = f"universal:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            data = extract_universal(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --------------------------------------------------------------------------
    # 2. INSTAGRAM ENDPOINTS
    # --------------------------------------------------------------------------
    @app.route("/api/instagram", methods=["GET", "POST"])
    def api_instagram():
        url = get_param("url") or get_param("link") or get_param("shortcode")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' or 'shortcode' parameter"}), 400
        cache_key = f"instagram:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            # Primary Cloud Engine
            if any(p in url for p in ["/reel/", "/p/", "/reels/", "/tv/"]):
                cloud_data = extract_primary_cloud(url)
                if cloud_data:
                    set_cached_media(cache_key, cloud_data)
                    return jsonify(cloud_data), 200

            ig = get_instagram_service()
            data = ig.dispatch_url(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/instagram/post", methods=["GET", "POST"])
    @app.route("/api/instagram/reel", methods=["GET", "POST"])
    def api_instagram_post():
        code = get_param("shortcode") or get_param("url")
        if not code:
            return jsonify({"status": "error", "message": "Missing 'shortcode' parameter"}), 400
        match = re.search(r"(?:/p/|/reel/|/reels/|/tv/)?([\w-]+)", code)
        clean_code = match.group(1) if match else code
        cache_key = f"instagram_post:{clean_code.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            # Primary Cloud Engine
            cloud_data = extract_primary_cloud(f"https://www.instagram.com/reel/{clean_code}/")
            if cloud_data:
                set_cached_media(cache_key, cloud_data)
                return jsonify(cloud_data), 200

            ig = get_instagram_service()
            data = ig.extract_post(clean_code)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/instagram/story", methods=["GET", "POST"])
    def api_instagram_story():
        username = get_param("username") or get_param("url")
        story_id = get_param("story_id")
        if not username:
            return jsonify({"status": "error", "message": "Missing 'username' parameter"}), 400
        match = re.search(r"/stories/([^/?#]+)(?:/(\d+))?", username)
        if match:
            username = match.group(1)
            story_id = story_id or match.group(2)
        try:
            ig = get_instagram_service()
            data = ig.extract_story(username, story_id)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/instagram/highlight", methods=["GET", "POST"])
    def api_instagram_highlight():
        hl_id = get_param("highlight_id") or get_param("id") or get_param("url")
        if not hl_id:
            return jsonify({"status": "error", "message": "Missing 'highlight_id' parameter"}), 400
        match = re.search(r"(\d+)", hl_id)
        clean_id = match.group(1) if match else hl_id
        cache_key = f"instagram_highlight:{clean_id.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            ig = get_instagram_service()
            data = ig.extract_highlight(clean_id)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/instagram/profile", methods=["GET", "POST"])
    def api_instagram_profile():
        user = get_param("username") or get_param("url")
        if not user:
            return jsonify({"status": "error", "message": "Missing 'username' parameter"}), 400
        match = re.search(r"(?:instagram\.com/|^@?)([A-Za-z0-9._]+)", user)
        clean_user = match.group(1) if match else user
        cache_key = f"instagram_profile:{clean_user.strip().lower()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            ig = get_instagram_service()
            data = ig.extract_profile(clean_user)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --------------------------------------------------------------------------
    # 3. SPOTIFY ENDPOINTS
    # --------------------------------------------------------------------------
    @app.route("/api/spotify", methods=["GET", "POST"])
    def api_spotify():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"spotify:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            data = fetch_spotify_tracks(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --------------------------------------------------------------------------
    # 4. APPLE MUSIC ENDPOINTS
    # --------------------------------------------------------------------------
    @app.route("/api/apple", methods=["GET", "POST"])
    @app.route("/api/apple-music", methods=["GET", "POST"])
    def api_apple():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"apple:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            data = fetch_apple_music_tracks(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --------------------------------------------------------------------------
    # 5. TERABOX ENDPOINTS & STREAMING PROXY
    # --------------------------------------------------------------------------
    @app.route("/api/terabox", methods=["GET", "POST"])
    def api_terabox():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cookies = get_param("cookies")
        cache_key = f"terabox:{url.strip()}"
        if not cookies:
            cached = get_cached_media(cache_key)
            if cached:
                return jsonify(cached), 200
        try:
            data = fetch_terabox_details(url, cookies_input=cookies)
            if not cookies:
                set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/terabox/download", methods=["GET"])
    def api_terabox_download():
        target_url = request.args.get("url") or request.args.get("dlink")
        filename = sanitize_filename(request.args.get("filename") or "terabox_media")
        if not target_url:
            return jsonify({"status": "error", "message": "Missing required 'url' parameter"}), 400

        cookies = load_effective_cookies()
        if "ndus" not in cookies and DEFAULT_NDUS:
            cookies["ndus"] = DEFAULT_NDUS

        if curl_requests:
            session = curl_requests.Session(impersonate="chrome110")
        else:
            session = requests.Session()
        session.cookies.update(cookies)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            "Referer": "https://www.terabox.app/",
            "Accept": "*/*"
        }

        try:
            res = session.get(target_url, headers=headers, stream=True, timeout=30, allow_redirects=True)
            def generate():
                for chunk in res.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk

            resp_headers = {
                "Content-Type": res.headers.get("Content-Type", "application/octet-stream"),
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
            if "Content-Length" in res.headers:
                resp_headers["Content-Length"] = res.headers["Content-Length"]

            return Response(generate(), status=res.status_code, headers=resp_headers)
        except Exception as ex:
            return jsonify({"status": "error", "message": f"Proxy streaming failed: {ex}"}), 500

    # --------------------------------------------------------------------------
    # 6. FACEBOOK ENDPOINTS
    # --------------------------------------------------------------------------
    @app.route("/api/facebook", methods=["GET", "POST"])
    @app.route("/api/fb", methods=["GET", "POST"])
    def api_facebook():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"facebook:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            # Primary Cloud Engine
            cloud_data = extract_primary_cloud(url)
            if cloud_data:
                set_cached_media(cache_key, cloud_data)
                return jsonify(cloud_data), 200

            # Native Fallback
            data = extract_ytdlp_media(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --------------------------------------------------------------------------
    # 7. YOUTUBE, TIKTOK, SNAPCHAT, TWITTER / X ENDPOINTS
    # --------------------------------------------------------------------------
    @app.route("/api/youtube", methods=["GET", "POST"])
    @app.route("/api/yt", methods=["GET", "POST"])
    def api_youtube():
        url = get_param("url")
        audio_only = str(get_param("audio", "false")).lower() in ("true", "1")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"youtube:{url.strip()}:{audio_only}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            # Pure PyTubeFix with bot-bypass - Zero YT-DLP
            data = extract_youtube_pytube(url, audio_only=audio_only)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/youtube/download", methods=["GET", "POST"])
    @app.route("/api/yt/download", methods=["GET", "POST"])
    def api_youtube_download():
        url = get_param("url")
        resolution = get_param("resolution")
        itag = get_param("itag")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        try:
            file_path, filename, err = download_youtube_pytube(url, resolution=resolution, itag=itag)
            if err or not file_path:
                return jsonify({"status": "error", "message": err or "Failed to download video"}), 500
            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype="video/mp4"
            )
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/tiktok", methods=["GET", "POST"])
    def api_tiktok():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"tiktok:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            # Primary Cloud Engine
            cloud_data = extract_primary_cloud(url)
            if cloud_data:
                set_cached_media(cache_key, cloud_data)
                return jsonify(cloud_data), 200

            # Native Fallback
            data = extract_ytdlp_media(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/snapchat", methods=["GET", "POST"])
    @app.route("/api/snap", methods=["GET", "POST"])
    def api_snapchat():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"snapchat:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            # Primary Cloud Engine
            cloud_data = extract_primary_cloud(url)
            if cloud_data:
                set_cached_media(cache_key, cloud_data)
                return jsonify(cloud_data), 200

            # Native Fallback
            data = extract_ytdlp_media(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --------------------------------------------------------------------------
    # 8. GENERAL HIGH-SPEED STREAMING DOWNLOAD PROXY
    # --------------------------------------------------------------------------
    @app.route("/api/download", methods=["GET"])
    def api_download_stream():
        target_url = request.args.get("url") or request.args.get("stream_url")
        if target_url and "api/file" in target_url:
            qs_parts = []
            if request.args.get("u"):
                qs_parts.append(f"u={quote(request.args.get('u'), safe='')}")
            if request.args.get("r"):
                qs_parts.append(f"r={quote(request.args.get('r'), safe='')}")
            if request.args.get("n"):
                qs_parts.append(f"n={quote(request.args.get('n'), safe='')}")
            if qs_parts and "?" not in target_url:
                target_url = f"{target_url}?{'&'.join(qs_parts)}"

        filename = sanitize_filename(request.args.get("filename") or "media_download")
        if not filename.endswith(".mp4"):
            filename += ".mp4"

        if not target_url:
            return jsonify({"status": "error", "message": "Missing required 'url' parameter"}), 400

        try:
            status, headers, generator = stream_media_url(target_url)
            resp_headers = {
                "Content-Type": headers.get("Content-Type", "video/mp4"),
                "Content-Disposition": f'attachment; filename="{filename}"',
            }
            if "Content-Length" in headers:
                resp_headers["Content-Length"] = headers["Content-Length"]

            return Response(generator, status=status, headers=resp_headers)
        except Exception as ex:
            return jsonify({"status": "error", "message": f"Proxy streaming failed: {ex}"}), 502

    @app.route("/api/twitter", methods=["GET", "POST"])
    @app.route("/api/x", methods=["GET", "POST"])
    def api_twitter():
        url = get_param("url")
        if not url:
            return jsonify({"status": "error", "message": "Missing 'url' parameter"}), 400
        cache_key = f"twitter:{url.strip()}"
        cached = get_cached_media(cache_key)
        if cached:
            return jsonify(cached), 200
        try:
            data = extract_ytdlp_media(url)
            set_cached_media(cache_key, data)
            return jsonify(data), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return app


# Module-level WSGI instance for Render / Gunicorn
app = create_app()


# ==============================================================================
# 10. CLI & DIRECT RUN ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    print(f"🚀 Starting XDOWNDERBACKEND Web API on http://{HOST}:{PORT} (v{APP_VERSION})")
    app.run(host=HOST, port=PORT, debug=False)
