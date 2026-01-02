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
import argparse
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
M3U8_FILE = SCRIPT_DIR / "../output/logs/all_m3u8_urls.txt"
OUTPUT_DIR = SCRIPT_DIR / "../output/videos"
COOKIES_FILE = SCRIPT_DIR / "../output/logs/cookies.txt"

def run_scraper(courses=None, headless=False):
    """Execute Selenium scraper in a thread"""
    print("🔍 Starting video scraper...")
    
    cmd = ["python3", "download_course_videos_selenium.py"]
    
    if courses:
        cmd.extend(["--courses"] + [str(c) for c in courses])
    
    if headless:
        cmd.append("--headless")
    
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    return result.returncode == 0

def monitor_and_download():
    """Monitor URL file and download IMMEDIATELY (tokens expire in 60min)"""
    print("📥 Starting immediate download monitor...\n")
    
    downloaded_urls = set()
    METADATA_FILE = SCRIPT_DIR / "../output/logs/video_metadata.jsonl"
    active_downloads = {}  # pid -> filename
    MAX_PARALLEL = 3  # Maximum 3 downloads at once
    
    while True:
        try:
            # Clean up completed downloads
            for pid in list(active_downloads.keys()):
                try:
                    os.kill(pid, 0)  # Check if process exists
                except OSError:
                    # Process finished
                    print(f"✅ Completed: {active_downloads[pid]}")
                    del active_downloads[pid]
            
            # Read metadata if available
            metadata_by_url = {}
            if METADATA_FILE.exists():
                import json
                with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            try:
                                meta = json.loads(line)
                                metadata_by_url[meta['url']] = meta
                            except:
                                pass
            
            # Read URLs from file
            if M3U8_FILE.exists():
                with open(M3U8_FILE, 'r') as f:
                    current_urls = [line.strip() for line in f 
                                  if line.strip() and line.strip().startswith('http')]
                
                # Detect new URLs
                new_urls = [url for url in current_urls if url not in downloaded_urls]
                
                if new_urls:
                    print(f"🆕 {len(new_urls)} new URLs detected")
                    
                    # Download EACH video but LIMIT parallel downloads
                    for url in new_urls:
                        # Wait if too many active downloads
                        while len(active_downloads) >= MAX_PARALLEL:
                            time.sleep(2)
                            # Clean up completed
                            for pid in list(active_downloads.keys()):
                                try:
                                    os.kill(pid, 0)
                                except OSError:
                                    print(f"✅ Completed: {active_downloads[pid]}")
                                    del active_downloads[pid]
                        
                        # Get metadata for this URL
                        meta = metadata_by_url.get(url, {})
                        course = meta.get('course', 'Unknown').replace('/', '-').replace(' ', '_')
                        category = meta.get('category', 0)
                        lesson = meta.get('lesson', 0)
                        
                        # Generate descriptive filename
                        filename = f"{course}_Cat{category:02d}_Lesson{lesson:02d}.mp4"
                        output_path = OUTPUT_DIR / filename
                        
                        print(f"⬇️  Downloading: {filename} ({len(active_downloads)+1}/{MAX_PARALLEL} active)")
                        
                        # Launch download with cookies and logs to file
                        log_file = OUTPUT_DIR / f"{filename}.log"
                        cmd = [
                            "yt-dlp",
                            url,
                            "-o", str(output_path),
                            "--no-check-certificate",
                            "-f", "best",
                            "--merge-output-format", "mp4",
                            "--concurrent-fragments", "3"
                        ]
                        
                        # Add cookies if file exists
                        if COOKIES_FILE.exists():
                            cmd.extend(["--cookies", str(COOKIES_FILE)])
                        
                        with open(log_file, 'w') as log:
                            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
                        
                        active_downloads[proc.pid] = filename
                        downloaded_urls.add(url)
            
            # Wait 2 seconds before checking again (faster response)
            time.sleep(2)
            
            # Check if scraper finished
            if M3U8_FILE.exists():
                with open(M3U8_FILE, 'r') as f:
                    content = f.read()
                    if "Total de medios" in content or "Total media" in content:
                        print("\n✅ Scraper completed, waiting for final downloads...")
                        time.sleep(30)  # Wait for all downloads to finish
                        break
                        
        except Exception as e:
            print(f"⚠️  Monitor error: {e}")
            time.sleep(5)
    
    print("✅ Download monitor finished")

def main():
    # Parse arguments
    parser = argparse.ArgumentParser(description='Complete pipeline: scraping and downloading in parallel')
    parser.add_argument('-c', '--courses', type=int, nargs='+', metavar='N',
                       help='Course numbers to process (e.g., -c 1 2 3)')
    parser.add_argument('--headless', action='store_true',
                       help='Run browser in headless mode')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🚀 COMPLETE PIPELINE - PARALLEL SCRAPING AND DOWNLOADING")
    print("=" * 70)
    print()
    
    if args.courses:
        print(f"📋 Processing only course(s): {', '.join(map(str, args.courses))}")
    if args.headless:
        print("👻 Running in headless mode")
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
        scraper_success = run_scraper(courses=args.courses, headless=args.headless)
        
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
