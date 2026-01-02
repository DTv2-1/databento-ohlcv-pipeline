#!/usr/bin/env python3
"""
Complete pipeline: Executes scraping and downloading in parallel
Calls download_course_videos_selenium.py and download_videos_auto.py
"""

import subprocess
import os
import sys
import time
import threading
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
M3U8_FILE = SCRIPT_DIR / "../output/logs/all_m3u8_urls.txt"
OUTPUT_DIR = SCRIPT_DIR / "../output/videos"

def run_scraper():
    """Execute Selenium scraper in a thread"""
    print("🔍 Starting video scraper...")
    result = subprocess.run(
        ["python3", "download_course_videos_selenium.py"],
        cwd=SCRIPT_DIR
    )
    return result.returncode == 0

def monitor_and_download():
    """Monitor URL file and download in parallel"""
    print("📥 Starting download monitor...\n")
    
    downloaded_urls = set()
    
    while True:
        try:
            # Read URLs from file
            if M3U8_FILE.exists():
                with open(M3U8_FILE, 'r') as f:
                    current_urls = [line.strip() for line in f 
                                  if line.strip() and line.strip().startswith('http')]
                
                # Detect new URLs
                new_urls = [url for url in current_urls if url not in downloaded_urls]
                
                if new_urls:
                    print(f"🆕 {len(new_urls)} new URLs detected")
                    
                    # Create temporary file with only new URLs
                    temp_file = SCRIPT_DIR / "../output/logs/temp_urls.txt"
                    with open(temp_file, 'w') as f:
                        for url in new_urls:
                            f.write(f"{url}\n")
                    
                    # Download new URLs with direct yt-dlp (faster)
                    print(f"⬇️  Downloading {len(new_urls)} videos...")
                    
                    result = subprocess.run([
                        "yt-dlp",
                        "-a", str(temp_file),
                        "-o", str(OUTPUT_DIR / "video_%(autonumber)03d_%(id)s.mp4"),
                        "--no-check-certificate",
                        "-f", "best",
                        "--merge-output-format", "mp4",
                        "--concurrent-fragments", "3",
                        "--progress",
                    ], cwd=SCRIPT_DIR)
                    
                    # Mark as downloaded
                    downloaded_urls.update(new_urls)
                    
                    # Clean up temporary file
                    temp_file.unlink(missing_ok=True)
            
            # Wait before checking again
            time.sleep(10)
            
            # Check if scraper finished (file has final header)
            if M3U8_FILE.exists():
                with open(M3U8_FILE, 'r') as f:
                    content = f.read()
                    if "Total de medios" in content:
                        print("\n✅ Scraper completed, processing final URLs...")
                        time.sleep(5)  # Give time for final downloads
                        break
                        
        except Exception as e:
            print(f"⚠️  Monitor error: {e}")
            time.sleep(5)
    
    print("✅ Download monitor finished")

def main():
    print("=" * 70)
    print("🚀 COMPLETE PIPELINE - PARALLEL SCRAPING AND DOWNLOADING")
    print("=" * 70)
    print()
    
    # Create directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Clean up previous URL file if exists
    if M3U8_FILE.exists():
        backup = M3U8_FILE.with_suffix('.txt.backup')
        M3U8_FILE.rename(backup)
        print(f"📦 Backup created: {backup.name}\n")
    
    # Start monitor in separate thread
    monitor_thread = threading.Thread(target=monitor_and_download, daemon=True)
    monitor_thread.start()
    
    # Execute scraper (blocks until finished)
    try:
        scraper_success = run_scraper()
        
        if not scraper_success:
            print("\n⚠️  Scraper finished with errors")
        
        # Wait for monitor to finish
        print("\n⏳ Waiting for downloads to complete...")
        monitor_thread.join(timeout=60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user")
        return
    
    # Final summary
    print("\n" + "=" * 70)
    print("📊 FINAL SUMMARY")
    print("=" * 70)
    
    # Count downloaded videos
    videos = list(OUTPUT_DIR.glob("*.mp4"))
    if videos:
        total_size = sum(v.stat().st_size for v in videos) / (1024 * 1024 * 1024)
        print(f"✅ {len(videos)} videos downloaded")
        print(f"💾 Total size: {total_size:.2f} GB")
        print(f"📁 Location: {OUTPUT_DIR}")
    else:
        print("⚠️  No videos downloaded")
    
    print("\n✨ Pipeline completed")

if __name__ == "__main__":
    main()
