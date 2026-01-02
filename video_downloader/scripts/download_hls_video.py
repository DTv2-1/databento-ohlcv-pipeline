#!/usr/bin/env python3
"""
Script to download HLS videos using yt-dlp
This script uses cookies from the Selenium session to download protected videos
"""

import subprocess
import json
import os
from pathlib import Path

# Base URL of HLS video found
HLS_BASE_URL = "https://content.apisystem.tech/hls/v2/memberships/KLSdqyqzjdv1UzrUfxKv/videos/cts-9b8613981c1020d9"

# Output directory (relative to scripts folder)
OUTPUT_DIR = "../output/videos"

def download_with_ytdlp(url, output_path, cookies=None):
    """
    Download HLS video using yt-dlp
    """
    print(f"📥 Downloading video with yt-dlp...")
    print(f"   URL: {url}")
    print(f"   Output: {output_path}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # yt-dlp command
    cmd = [
        "yt-dlp",
        url,
        "-o", output_path,
        "--no-check-certificate",
        "-f", "best",
        "--merge-output-format", "mp4",
    ]
    
    # Add cookies if available
    if cookies and os.path.exists(cookies):
        cmd.extend(["--cookies", cookies])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Download completed successfully")
            return True
        else:
            print(f"❌ Download error:")
            print(result.stderr)
            return False
    except FileNotFoundError:
        print("❌ yt-dlp is not installed")
        print("\nTo install it:")
        print("  brew install yt-dlp")
        print("  or")
        print("  pip3 install yt-dlp")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def download_with_ffmpeg(m3u8_url, output_path, cookies_header=None):
    """
    Download HLS video using ffmpeg
    """
    print(f"📥 Downloading video with ffmpeg...")
    print(f"   URL: {m3u8_url}")
    print(f"   Output: {output_path}")
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # ffmpeg command
    cmd = [
        "ffmpeg",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
        "-i", m3u8_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        output_path
    ]
    
    # Add cookie headers if available
    if cookies_header:
        cmd.insert(1, "-headers")
        cmd.insert(2, f"Cookie: {cookies_header}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Download completed successfully")
            return True
        else:
            print(f"❌ Download error:")
            print(result.stderr)
            return False
    except FileNotFoundError:
        print("❌ ffmpeg is not installed")
        print("\nTo install it:")
        print("  brew install ffmpeg")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 70)
    print("🎬 HLS VIDEO DOWNLOADER")
    print("=" * 70)
    
    # Search for downloaded m3u8 files
    m3u8_files = list(Path(OUTPUT_DIR).glob("*.mp4"))
    
    if m3u8_files:
        print(f"\n📂 Files found in {OUTPUT_DIR}:")
        for f in m3u8_files:
            print(f"   - {f.name} ({f.stat().st_size} bytes)")
    
    # Build complete manifest URL
    # We need to get the complete m3u8 manifest URL
    print("\n💡 To download the complete video, you need:")
    print("   1. The complete URL of the .m3u8 file (manifest)")
    print("   2. Authentication cookies from the session")
    print("\nUsage example:")
    print(f"   yt-dlp 'COMPLETE_M3U8_URL' -o '{OUTPUT_DIR}/video.mp4'")
    print("\nOr with ffmpeg:")
    print(f"   ffmpeg -i 'COMPLETE_M3U8_URL' -c copy '{OUTPUT_DIR}/video.mp4'")
    
    # Try with the base URL we found
    print("\n🔄 Trying with found base URL...")
    
    # Try different variations
    urls_to_try = [
        f"{HLS_BASE_URL}_master.m3u8",
        f"{HLS_BASE_URL}.m3u8",
        f"{HLS_BASE_URL}_playlist.m3u8",
        f"{HLS_BASE_URL}_720p.m3u8",
    ]
    
    output_file = f"{OUTPUT_DIR}/apex_welcome_video.mp4"
    
    for url in urls_to_try:
        print(f"\nTesting: {url}")
        if download_with_ytdlp(url, output_file):
            break
        print("   ⚠️  Invalid URL, trying next...")
    else:
        print("\n" + "=" * 70)
        print("💡 MANUAL INSTRUCTIONS")
        print("=" * 70)
        print("\nThe video uses HLS streaming with protected segments.")
        print("To download it manually:")
        print("\n1. Open browser DevTools (F12)")
        print("2. Go to Network tab")
        print("3. Filter by '.m3u8'")
        print("4. Play the video")
        print("5. Copy the complete URL of the .m3u8 file")
        print("6. Use yt-dlp to download it:")
        print("\n   yt-dlp 'COMPLETE_M3U8_URL' -o 'video.mp4'")
