#!/usr/bin/env python3
"""
Custom scraper for marczellklein.com with direct login link
Uses loginCode parameter for automatic authentication
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import json
import re
import os
import argparse
import subprocess
import threading
import queue
from pathlib import Path
import requests
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / '.env')

# Ensure we are in the correct folder
SCRIPT_DIR = Path(__file__).parent
os.chdir(SCRIPT_DIR)

# Create directories if they don't exist
Path("../output/videos").mkdir(parents=True, exist_ok=True)
Path("../output/screenshots").mkdir(parents=True, exist_ok=True)
Path("../output/html").mkdir(parents=True, exist_ok=True)
Path("../output/logs").mkdir(parents=True, exist_ok=True)

# Credentials from environment
EMAIL = os.getenv('VIDEO_DOWNLOADER_EMAIL')
PASSWORD = os.getenv('VIDEO_DOWNLOADER_PASSWORD')

if not EMAIL or not PASSWORD:
    raise ValueError("VIDEO_DOWNLOADER_EMAIL and VIDEO_DOWNLOADER_PASSWORD must be set in .env file")

# URLs - CUSTOM LOGIN LINK
BASE_URL = "https://members.marczellklein.com"
# Direct link with loginCode - bypasses normal login flow
DIRECT_LOGIN_URL = "https://members.marczellklein.com?email=petedavisesq@gmail.com&loginCode=@9vVRwL&user=56319fe7-a1c6-42da-86be-181ad3987f8e&redirectUrl=courses/library-v2"
COURSE_URL = "https://members.marczellklein.com/courses/library-v2"

# Output directories (relative to scripts folder)
OUTPUT_DIR = "../output/videos"
SCREENSHOTS_DIR = "../output/screenshots"
HTML_DIR = "../output/html"
LOGS_DIR = "../output/logs"

# Variables for parallel download
MAX_DOWNLOAD_WORKERS = 3
download_queue = queue.Queue()
download_stats = {
    'captured': 0,
    'downloaded': 0,
    'failed': 0,
    'skipped': 0
}
download_stats_lock = threading.Lock()
download_pbar = None

def download_worker(worker_id):
    """Worker that downloads videos from queue in background"""
    global download_pbar
    
    while True:
        try:
            item = download_queue.get(timeout=2)
            if item is None:  # Termination signal
                break
            
            video_num, video_id, url = item
            output_name = f"video_{video_num:03d}_{video_id}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_name)
            
            # If already exists, skip
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                if download_pbar:
                    download_pbar.write(f"   ⏭️  [{worker_id}] Already exists: {output_name} ({size_mb:.1f} MB)")
                with download_stats_lock:
                    download_stats['skipped'] += 1
                download_queue.task_done()
                continue
            
            # Download with yt-dlp
            cmd = [
                "yt-dlp",
                url,
                "-o", output_path,
                "--no-check-certificate",
                "-f", "best",
                "--merge-output-format", "mp4",
                "--quiet",
                "--no-warnings"
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                
                if result.returncode == 0 and os.path.exists(output_path):
                    size_mb = os.path.getsize(output_path) / (1024 * 1024)
                    if download_pbar:
                        download_pbar.write(f"   ✅ [{worker_id}] {output_name} ({size_mb:.1f} MB)")
                    with download_stats_lock:
                        download_stats['downloaded'] += 1
                        if download_pbar:
                            download_pbar.update(1)
                else:
                    if download_pbar:
                        download_pbar.write(f"   ❌ [{worker_id}] {output_name} - Download error")
                    with download_stats_lock:
                        download_stats['failed'] += 1
            except subprocess.TimeoutExpired:
                if download_pbar:
                    download_pbar.write(f"   ⏰ [{worker_id}] {output_name} - Timeout (>5min)")
                with download_stats_lock:
                    download_stats['failed'] += 1
            except Exception as e:
                if download_pbar:
                    download_pbar.write(f"   ❌ [{worker_id}] {output_name} - {str(e)[:50]}")
                with download_stats_lock:
                    download_stats['failed'] += 1
            
            download_queue.task_done()
            
        except queue.Empty:
            continue

class SeleniumCourseDownloader:
    def __init__(self, headless=False, course_filter=None):
        """
        Initialize the downloader
        headless: If True, browser runs without graphical interface
        course_filter: List of course indices to process (1-based), None for all
        """
        self.headless = headless
        self.course_filter = course_filter
        self.captured_video_ids = set()  # Track already captured video IDs
        self.output_dir = OUTPUT_DIR  # Directory to save files
        self.driver = None
        self.active_downloads = {}  # Track active downloads {filename: thread}
        self.max_parallel_downloads = 3  # Maximum parallel downloads
        self.checkpoint_file = Path("../output/logs/checkpoint.json")
        self.batch_size = 3  # Process 3 lessons per browser session
        
        # Load already downloaded videos from files
        self.load_downloaded_videos()
        
        self.setup_driver()
    
    def load_downloaded_videos(self):
        """Check existing .mp4 files and report statistics"""
        videos_dir = Path("../output/videos")
        if not videos_dir.exists():
            return
        
        # Search in both root and subfolders
        mp4_files = list(videos_dir.glob("*.mp4")) + list(videos_dir.glob("*/*.mp4"))
        if not mp4_files:
            return
            
        print(f"\n📂 Checking existing downloads...")
        print(f"   ✓ Found {len(mp4_files)} .mp4 files")
        
        # Validate files: check size (should be > 1MB for valid video)
        valid_count = 0
        invalid_count = 0
        min_size = 1 * 1024 * 1024  # 1MB minimum
        
        for mp4_file in mp4_files:
            try:
                file_size = mp4_file.stat().st_size
                if file_size > min_size:
                    valid_count += 1
                else:
                    invalid_count += 1
                    print(f"   ⚠️  Invalid file (too small): {mp4_file.name} ({file_size:,} bytes)")
            except:
                invalid_count += 1
        
        print(f"   ✓ Valid downloads: {valid_count}")
        if invalid_count > 0:
            print(f"   ⚠️  Invalid/incomplete: {invalid_count} (will re-download if encountered)")
        
        print(f"   💡 Duplicate detection: BY FILENAME (not by video_id)")
        print()
    
    def save_checkpoint(self, course_index, category_number, lesson_number):
        """Save current progress"""
        checkpoint = {
            'course_index': course_index,
            'category_number': category_number,
            'lesson_number': lesson_number,
            'completed_video_ids': list(self.captured_video_ids),
            'timestamp': time.time()
        }
        with open(self.checkpoint_file, 'w') as f:
            json.dump(checkpoint, f, indent=2)
        print(f"   💾 Checkpoint saved: Course {course_index}, Cat {category_number}, Lesson {lesson_number}")
    
    def load_checkpoint(self):
        """Load previous progress with validation"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r') as f:
                    checkpoint = json.load(f)
                
                # Validate structure
                required_keys = ['course_index', 'category_number', 'lesson_number']
                if not all(key in checkpoint for key in required_keys):
                    print("   ⚠️  Invalid checkpoint structure - removing")
                    self.checkpoint_file.unlink()
                    return None
                
                # Validate ranges
                course_idx = checkpoint['course_index']
                cat_num = checkpoint['category_number']
                lesson_num = checkpoint['lesson_number']
                
                if not (0 <= course_idx <= 10):
                    print(f"   ⚠️  Invalid course_index {course_idx} - removing checkpoint")
                    self.checkpoint_file.unlink()
                    return None
                
                if not (1 <= cat_num <= 50):
                    print(f"   ⚠️  Invalid category_number {cat_num} - removing checkpoint")
                    self.checkpoint_file.unlink()
                    return None
                
                if not (0 <= lesson_num <= 500):
                    print(f"   ⚠️  Invalid lesson_number {lesson_num} - removing checkpoint")
                    self.checkpoint_file.unlink()
                    return None
                
                # Check age (7 days max)
                if 'timestamp' in checkpoint:
                    checkpoint_age = time.time() - checkpoint['timestamp']
                    if checkpoint_age > 7 * 24 * 3600:
                        print(f"   ⚠️  Checkpoint too old ({checkpoint_age/(24*3600):.1f} days) - removing")
                        self.checkpoint_file.unlink()
                        return None
                
                self.captured_video_ids = set(checkpoint.get('completed_video_ids', []))
                print(f"   📂 Checkpoint loaded: Course {course_idx}, Cat {cat_num}, Lesson {lesson_num}")
                print(f"      {len(self.captured_video_ids)} videos already processed")
                return checkpoint
            except Exception as e:
                print(f"   ⚠️  Checkpoint load error: {e} - removing")
                self.checkpoint_file.unlink()
                return None
        return None
    
    def wait_for_downloads(self):
        """Wait for all active downloads to complete"""
        if not self.active_downloads:
            return
        
        print(f"\n⏳ Waiting for {len(self.active_downloads)} downloads to complete...")
        
        while self.active_downloads:
            time.sleep(5)
            # Check finished downloads
            finished = [fn for fn, thread in self.active_downloads.items() if not thread.is_alive()]
            for fn in finished:
                print(f"   ✅ Completed: {fn}")
                del self.active_downloads[fn]
            
            if self.active_downloads:
                print(f"   ⏳ Still downloading: {len(self.active_downloads)} videos...")
        
        print("✅ All downloads completed!\n")
    
    def close_driver(self):
        """Close browser and clean up driver"""
        if self.driver:
            try:
                print("\n🔄 Closing browser...")
                self.driver.quit()
                self.driver = None
                print("   ✅ Browser closed")
            except Exception as e:
                print(f"   ⚠️  Error closing browser: {e}")
    
    def reopen_driver(self):
        """Reopen browser with fresh session"""
        print("\n🔄 Reopening browser with fresh session...")
        self.setup_driver()
        print("   ✅ Fresh browser ready")
    
    def process_course_in_batches(self, course_index, course_url, course_name):
        """Process a course in batches with browser restart every N lessons
        
        Args:
            course_index: Course number
            course_url: URL of the course
            course_name: Name of the course
        """
        print(f"\n{'='*80}")
        print(f"📚 COURSE #{course_index + 1}: {course_name}")
        print(f"🔗 {course_url}")
        print(f"{'='*80}")
        
        # Load checkpoint if exists
        checkpoint = self.load_checkpoint()
        if checkpoint:
            checkpoint_course = checkpoint.get('course_index')
            if checkpoint_course != course_index:
                print(f"   ⚠️  Checkpoint is for course {checkpoint_course + 1}, but processing course {course_index + 1}")
                print(f"   🗑️  Removing incompatible checkpoint")
                self.checkpoint_file.unlink()
                checkpoint = None
        
        if checkpoint and checkpoint.get('course_index') == course_index:
            start_category = checkpoint.get('category_number', 1)
            start_lesson = checkpoint.get('lesson_number', 0)
            
            # CRITICAL FIX: Verify which files actually exist and find first missing lesson
            # The checkpoint might say "Lesson 12" but Lesson 9 could be missing
            course_name_clean = course_name.replace('/', '-').replace(' ', '_')
            subfolder = ""
            if course_name_clean.startswith("APEX"):
                subfolder = "APEX/"
            elif course_name_clean.startswith("Hypnosis"):
                subfolder = "Hypnosis/"
            elif course_name_clean.startswith("The_Simple_Course"):
                subfolder = "Simple_Course/"
            
            videos_dir = Path("../output/videos")
            
            # Check for missing files in the checkpoint category
            missing_lesson = None
            for lesson_num in range(1, start_lesson + 2):  # Check lessons 1 to start_lesson+1
                file_pattern = f"{subfolder}{course_name_clean}_Cat{start_category:02d}_Lesson{lesson_num:02d}.mp4"
                file_path = videos_dir / file_pattern
                if not file_path.exists():
                    missing_lesson = lesson_num
                    break
            
            if missing_lesson is not None:
                # Adjust start_lesson to the first missing lesson (0-indexed)
                adjusted_start_lesson = missing_lesson - 1
                print(f"\n📍 Checkpoint: Cat {start_category}, Lesson {start_lesson + 1}")
                print(f"   ⚠️  Found missing file: Lesson {missing_lesson}")
                print(f"   🔄 Adjusting resume point to: Cat {start_category}, Lesson {missing_lesson}")
                start_lesson = adjusted_start_lesson
            else:
                print(f"\n📍 Resuming from checkpoint: Cat {start_category}, Lesson {start_lesson + 1}")
        else:
            start_category = 1
            start_lesson = 0
            print(f"\n🆕 Starting fresh: Cat {start_category}, Lesson {start_lesson + 1}")
        
        batch_number = 0
        
        while True:
            batch_number += 1
            print(f"\n{'='*80}")
            print(f"🎯 BATCH #{batch_number} - Processing up to {self.batch_size} lessons")
            print(f"   Starting from: Cat {start_category}, Lesson {start_lesson + 1}")
            print(f"{'='*80}")
            
            # Navigate to course
            print(f"\n🌐 Navigating to course...")
            self.driver.get(course_url)
            time.sleep(5)
            
            # Reset batch counter
            self.lessons_processed_this_batch = 0
            
            # Process batch
            videos, last_cat, last_lesson = self.find_videos(
                course_index=course_index,
                course_name=course_name,
                start_category=start_category,
                start_lesson=start_lesson,
                max_lessons=self.batch_size
            )
            
            # Check if we processed any lessons
            lessons_this_batch = self.lessons_processed_this_batch
            if lessons_this_batch == 0:
                print("\n✅ No more lessons to process - course complete!")
                break
            
            import datetime
            end_time = datetime.datetime.now()
            print(f"\n[{end_time.strftime('%H:%M:%S')}] ✅ Batch completed: {lessons_this_batch} lessons processed")
            print(f"   📍 Stopped at: Cat {last_cat}, Lesson {last_lesson + 1}")
            
            # Update position for next batch
            # IMPORTANT: last_lesson is 0-indexed (Lesson 1 = 0, Lesson 2 = 1, etc.)
            # We want to continue from the NEXT lesson, so we keep last_lesson as-is
            # The skip logic in find_videos() will handle: lessons_processed < start_lesson
            start_category = last_cat
            start_lesson = last_lesson  # Don't add 1 here, let find_videos() handle it
            
            # Save checkpoint with current position
            self.save_checkpoint(course_index, start_category, start_lesson)
            print(f"💾 Checkpoint saved: Cat {start_category}, Lesson {start_lesson + 1}")
            
            # Wait for all downloads to complete
            self.wait_for_downloads()
            
            # Close browser
            self.close_driver()
            
            # Sleep before reopening (avoid rate limiting)
            print("\n😴 Sleeping 10 seconds before next batch...")
            time.sleep(10)
            
            # Reopen browser
            self.reopen_driver()
            
            # Login again
            print("\n🔐 Logging in...")
            self.login()
            
            print(f"\n🔄 Ready for next batch\n")
        
    def setup_driver(self):
        """Configure Chrome driver"""
        print("🔧 Setting up Chrome browser...")
        
        options = webdriver.ChromeOptions()
        
        if self.headless:
            options.add_argument('--headless=new')  # New headless mode (more stable)
            options.add_argument('--window-size=1920,1080')  # Set window size in headless
        
        # Options for better performance and compatibility
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-gpu')  # Disable GPU in headless
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-extensions')
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Enable network logs to capture requests
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        # User agent (realistic)
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Add preferences to avoid detection
        prefs = {
            'profile.default_content_setting_values.notifications': 2,
            'profile.default_content_settings.popups': 0,
        }
        options.add_experimental_option('prefs', prefs)
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            
            # Minimize window if not headless (to avoid blocking other windows)
            if not self.headless:
                self.driver.minimize_window()
                print("   ✓ Window minimized to avoid blocking screen")
            
            # Execute JavaScript to hide webdriver property
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })
            
            # Activate Chrome DevTools Protocol to capture network requests
            self.driver.execute_cdp_cmd('Network.enable', {})
            
            print("✅ Chrome browser started")
        except Exception as e:
            print(f"❌ Error starting Chrome: {e}")
            print("\nMake sure you have ChromeDriver installed:")
            print("  brew install chromedriver")
            raise
    
    def export_cookies_for_ytdlp(self):
        """Export cookies in Netscape format for yt-dlp"""
        try:
            cookies = self.driver.get_cookies()
            cookies_file = Path("../output/logs/cookies.txt")
            
            with open(cookies_file, 'w') as f:
                # Netscape HTTP Cookie File header
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# This file was generated by Selenium\n\n")
                
                for cookie in cookies:
                    # Netscape format: domain, flag, path, secure, expiration, name, value
                    domain = cookie.get('domain', '')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = cookie.get('path', '/')
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expiry = cookie.get('expiry', 0)
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
            
            print(f"   ✅ Cookies exported to {cookies_file}")
        except Exception as e:
            print(f"   ⚠️  Could not export cookies: {e}")
    
    def download_video_with_selenium_session(self, m3u8_url, filename):
        """Download HLS video using requests with Selenium cookies/headers"""
        try:
            import subprocess
            import threading
            
            # Wait if too many downloads active
            while len(self.active_downloads) >= self.max_parallel_downloads:
                # Clean up finished downloads
                finished = [fn for fn, thread in self.active_downloads.items() if not thread.is_alive()]
                for fn in finished:
                    print(f"         ✅ Completed: {fn}")
                    del self.active_downloads[fn]
                
                if len(self.active_downloads) >= self.max_parallel_downloads:
                    time.sleep(2)
            
            # Create requests session with Selenium cookies
            session = requests.Session()
            
            # Copy all cookies from Selenium
            selenium_cookies = self.driver.get_cookies()
            for cookie in selenium_cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'))
            
            # Set headers matching Selenium browser
            session.headers.update({
                'User-Agent': self.driver.execute_script("return navigator.userAgent;"),
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': self.driver.current_url,
                'Origin': 'https://members.marczellklein.com'
            })
            
            output_path = Path(f"../output/videos/{filename}")
            
            # Create subfolder if filename contains course prefix
            if filename.startswith("APEX_"):
                output_path = Path(f"../output/videos/APEX/{filename}")
            elif filename.startswith("Hypnosis_"):
                output_path = Path(f"../output/videos/Hypnosis/{filename}")
            elif filename.startswith("The_Simple_Course_"):
                output_path = Path(f"../output/videos/Simple_Course/{filename}")
            
            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            log_file = output_path.with_suffix('.mp4.log')
            
            # Download using yt-dlp with custom cookies (via --add-header)
            # We'll pass the session cookies as a file
            cookies_temp = Path(f"../output/logs/temp_cookies_{filename}.txt")
            with open(cookies_temp, 'w') as f:
                f.write("# Netscape HTTP Cookie File\n\n")
                for cookie in selenium_cookies:
                    domain = cookie.get('domain', '')
                    flag = 'TRUE' if domain.startswith('.') else 'FALSE'
                    path = cookie.get('path', '/')
                    secure = 'TRUE' if cookie.get('secure', False) else 'FALSE'
                    expiry = cookie.get('expiry', 0)
                    name = cookie.get('name', '')
                    value = cookie.get('value', '')
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{name}\t{value}\n")
            
            # Launch yt-dlp in background with cookies and custom headers
            def run_download():
                try:
                    with open(log_file, 'w') as log:
                        user_agent = self.driver.execute_script("return navigator.userAgent;")
                        referer = self.driver.current_url
                        
                        subprocess.run([
                            "yt-dlp",
                            m3u8_url,
                            "-o", str(output_path),
                            "--cookies", str(cookies_temp),
                            "--add-header", f"User-Agent: {user_agent}",
                            "--add-header", f"Referer: {referer}",
                            "--add-header", "Origin: https://members.marczellklein.com",
                            "--no-check-certificate",
                            "-f", "best",
                            "--merge-output-format", "mp4",
                            "--concurrent-fragments", "3"
                        ], stdout=log, stderr=subprocess.STDOUT)
                finally:
                    # Clean up temp cookies
                    try:
                        cookies_temp.unlink()
                    except:
                        pass
            
            # Start download in background thread
            download_thread = threading.Thread(target=run_download, daemon=True)
            download_thread.start()
            
            # Track active download
            self.active_downloads[filename] = download_thread
            
            print(f"         ⬇️  Download started: {filename} ({len(self.active_downloads)}/{self.max_parallel_downloads} active)")
            
        except Exception as e:
            print(f"         ❌ Download error: {str(e)[:60]}")
    
    def login(self):
        """Authenticate on the site using direct login link"""
        print("\n🔐 Starting login with direct link...")
        
        try:
            # Use the direct login URL with loginCode
            print(f"   Navigating to direct login URL...")
            self.driver.get(DIRECT_LOGIN_URL)
            time.sleep(8)  # Wait for redirect and authentication
            
            # Save screenshot
            self.driver.save_screenshot('../output/screenshots/step1_direct_login.png')
            print("   Screenshot saved: step1_direct_login.png")
            
            # Check current URL after redirect
            current_url = self.driver.current_url
            page_source = self.driver.page_source.lower()
            
            print(f"   Current URL: {current_url}")
            
            # Save page after login
            with open('../output/html/page_after_direct_login.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            # Look for successful login indicators
            success_indicators = [
                'logout', 'sign out', 'dashboard', 'welcome', 
                'courses', 'library', 'account', 'profile'
            ]
            
            for indicator in success_indicators:
                if indicator in page_source:
                    print(f"✅ Login successful (found: '{indicator}')")
                    return True
            
            # Check if we're on the courses page
            if 'courses' in current_url.lower() or 'library' in current_url.lower():
                print("✅ Login successful (redirected to courses)")
                return True
            
            # If direct login didn't work, fallback to normal login
            print("   ⚠️  Direct login may not have worked, trying normal login...")
            return self._fallback_login()
            
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
        except Exception as e:
            print(f"❌ Error during login: {e}")
            self.driver.save_screenshot('../output/screenshots/error_login.png')
            with open('../output/html/page_source_exception.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            return False
    
    def _find_login_elements(self):
        """Search for login elements on current page"""
        selectors = [
            "//button[contains(text(), 'Sign In')]",
            "//button[contains(text(), 'Log In')]",
            "//a[contains(text(), 'Sign In')]",
            "//input[@type='email']",
        ]
        
        for selector in selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if elements:
                    return elements[0]
            except:
                continue
        return None
    
    def _find_email_field(self):
        """Search for email field"""
        selectors = [
            (By.ID, "sign-in-form-email"),  # Site-specific ID
            (By.XPATH, "//div[@id='sign-in-form-email']//input"),  # Input inside div
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[contains(@name, 'email')]"),
            (By.XPATH, "//input[contains(@id, 'email')]"),
            (By.XPATH, "//input[contains(@placeholder, 'Email') or contains(@placeholder, 'email')]"),
            (By.XPATH, "//input[@type='text' and contains(@placeholder, 'Email')]"),
        ]
        
        for by, selector in selectors:
            try:
                elements = self.driver.find_elements(by, selector)
                if elements:
                    # If we found a div, search for input inside
                    if elements[0].tag_name == 'div':
                        inputs = elements[0].find_elements(By.TAG_NAME, 'input')
                        if inputs:
                            print(f"   ✓ Email field found: {selector}")
                            return inputs[0]
                    else:
                        print(f"   ✓ Email field found: {selector}")
                        return elements[0]
            except:
                continue
        return None
    
    def _find_password_field(self):
        """Search for password field"""
        selectors = [
            (By.ID, "sign-in-form-password"),  # Site-specific ID
            (By.XPATH, "//div[@id='sign-in-form-password']//input"),  # Input inside div
            (By.XPATH, "//input[@type='password']"),
            (By.XPATH, "//input[contains(@name, 'password')]"),
            (By.XPATH, "//input[contains(@id, 'password')]"),
        ]
        
        for by, selector in selectors:
            try:
                elements = self.driver.find_elements(by, selector)
                if elements:
                    # If we found a div, search for input inside
                    if elements[0].tag_name == 'div':
                        inputs = elements[0].find_elements(By.TAG_NAME, 'input')
                        if inputs:
                            print(f"   ✓ Password field found: {selector}")
                            return inputs[0]
                    else:
                        print(f"   ✓ Password field found: {selector}")
                        return elements[0]
            except:
                continue
        return None
    
    def _find_submit_button(self):
        """Search for submit button"""
        selectors = [
            (By.ID, "login--button"),  # Site-specific ID
            (By.XPATH, "//button[@id='login--button']"),
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//button[contains(text(), 'Sign In')]"),
            (By.XPATH, "//button[contains(text(), 'Log In')]"),
            (By.XPATH, "//input[@type='submit']"),
        ]
        
        for by, selector in selectors:
            try:
                elements = self.driver.find_elements(by, selector)
                if elements:
                    print(f"   ✓ Submit button found: {selector}")
                    return elements[0]
            except:
                continue
        return None
    
    def _fallback_login(self):
        """Fallback to normal login if direct link fails"""
        print("   Attempting fallback login method...")
        
        # Try direct access to course page
        print(f"   Attempting direct access to: {COURSE_URL}")
        self.driver.get(COURSE_URL)
        time.sleep(5)
        
        # Look for form fields
        email_field = self._find_email_field()
        password_field = self._find_password_field()
        
        if not email_field or not password_field:
            print("   ❌ Fallback login failed - no form fields")
            return False
        
        # Fill form
        print("   Entering credentials...")
        email_field.clear()
        email_field.send_keys(EMAIL)
        time.sleep(0.5)
        
        password_field.clear()
        password_field.send_keys(PASSWORD)
        time.sleep(0.5)
        
        # Submit
        submit_button = self._find_submit_button()
        if submit_button:
            submit_button.click()
        else:
            password_field.send_keys('\n')
        
        time.sleep(5)
        
        # Check success
        current_url = self.driver.current_url
        if 'courses' in current_url.lower():
            print("✅ Fallback login successful")
            return True
        
        print("❌ Fallback login failed")
        return False
    
    def navigate_to_course(self, course_index, course_xpath):
        """
        Navigate to a specific course by its index
        
        Args:
            course_index: Course number (1, 2, 3)
            course_xpath: Course XPath (e.g.: '//*[@id="product-list"]/div[1]')
        """
        print(f"\n📚 Navigating to course #{course_index}...")
        
        try:
            # Return to main course page
            if course_index > 1:
                print("   Returning to course list...")
                self.driver.get(COURSE_URL)
                time.sleep(3)
            
            # Save screenshot of course page
            self.driver.save_screenshot(f'../output/screenshots/step6_course_list_{course_index}.png')
            
            # Save HTML
            with open(f'../output/html/course_page_{course_index}.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            # Search for course card using provided XPath
            print(f"   Looking for course with XPath: {course_xpath}")
            
            try:
                course_card = self.driver.find_element(By.XPATH, course_xpath)
                
                # Get course name
                try:
                    course_title = course_card.find_element(By.XPATH, ".//h4[@id='product-card-title']").text
                    print(f"   ✓ Course found: '{course_title}'")
                except:
                    course_title = f"Course {course_index}"
                    print(f"   ✓ Course #{course_index} found")
                
                # Scroll to element to ensure it's visible
                self.driver.execute_script("arguments[0].scrollIntoView(true);", course_card)
                time.sleep(1)
                
                # Click on course card
                print(f"   Clicking on course...")
                course_card.click()
                time.sleep(4)
                
                self.driver.save_screenshot(f'../output/screenshots/step7_course_{course_index}_clicked.png')
                
                # Search for "Start Course", "Resume Course" or "Continue" button
                print("   Looking for start button...")
                start_button_selectors = [
                    "//button[contains(text(), 'Start Course')]",
                    "//button[contains(text(), 'Resume Course')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[@id='load-next-post']",
                    "//button[contains(@class, 'hero-button')]",
                    "//button[contains(@class, 'primary-text')]",
                ]
                
                start_button = None
                for selector in start_button_selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        if elements:
                            start_button = elements[0]
                            print(f"   ✓ Button found: {start_button.text}")
                            break
                    except:
                        continue
                
                if start_button:
                    print("   Clicking on button...")
                    start_button.click()
                    time.sleep(5)
                    
                    self.driver.save_screenshot(f'../output/screenshots/step8_course_{course_index}_started.png')
                    print(f"   ✓ Navigated to: {self.driver.current_url}")
                else:
                    print("   ⚠️  Start button not found, continuing...")
                
                return True, course_title
                
            except Exception as e:
                print(f"   ❌ Course not found with XPath: {course_xpath}")
                print(f"   Error: {e}")
                return False, None
            
        except Exception as e:
            print(f"❌ Error navigating to course: {e}")
            return False, None
    
    def find_videos(self, course_index=0, course_name="Unknown", start_category=1, start_lesson=0, max_lessons=None):
        """Find videos on current course page - supports batch processing
        
        Args:
            course_index: Course number
            course_name: Name of the course
            start_category: Category to start from (1-indexed)
            start_lesson: Lesson to start from in that category (0-indexed)
            max_lessons: Maximum lessons to process before returning (None = all)
        """
        import datetime
        start_time = datetime.datetime.now()
        print(f"\n🔍 [{start_time.strftime('%H:%M:%S')}] Navigating through course playlist (from Cat {start_category}, Lesson {start_lesson+1})...")
        
        all_videos_urls = []
        self.current_course_name = course_name  # Save for later use
        self.lessons_processed_this_batch = 0  # Counter for batch
        self.last_category_processed = start_category  # Track last category
        self.last_lesson_processed = start_lesson  # Track last lesson in that category
        
        # Wait for page to load
        time.sleep(5)
        
        # STEP 1: Detect course container type
        print("\n🔍 Detecting course structure...")
        playlist_container_xpath = None
        prev_button_xpath = None
        next_button_xpath = None
        
        # Wait more time to load
        time.sleep(7)
        
        # Variable to save detected structure
        structure_type = None
        
        # Try playlist-wrapper first
        try:
            self.driver.find_element(By.XPATH, '//*[@id="playlist-wrapper"]/div[2]')
            playlist_container_xpath = '//*[@id="playlist-wrapper"]/div[2]'
            prev_button_xpath = '//*[@id="playlist-wrapper"]/div[3]/div[1]/button'
            next_button_xpath = '//*[@id="playlist-wrapper"]/div[3]/div[2]/button'
            structure_type = "playlist-wrapper"
            print("   ✓ Structure: playlist-wrapper")
        except:
            # Try post-playlist
            try:
                self.driver.find_element(By.XPATH, '//*[@id="post-playlist"]/div[2]')
                playlist_container_xpath = '//*[@id="post-playlist"]/div[2]'
                prev_button_xpath = '//*[@id="post-playlist"]/div[3]/div[1]/button'
                next_button_xpath = '//*[@id="post-playlist"]/div[3]/div[2]/button'
                structure_type = "post-playlist"
                print("   ✓ Structure: post-playlist")
            except:
                # Try alternative structure (search for any container with videos)
                print("   ⚠️  Known structures not found, looking for alternatives...")
                
                # Search by class or ID containing "playlist" or "post"
                alternative_containers = [
                    '//div[contains(@id, "playlist")]',
                    '//div[contains(@id, "post")]',
                    '//div[contains(@class, "playlist")]',
                    '//div[contains(@class, "post-content")]',
                ]
                
                for xpath in alternative_containers:
                    try:
                        container = self.driver.find_element(By.XPATH, xpath)
                        playlist_container_xpath = xpath
                        print(f"   ✓ Alternative structure found: {xpath[:50]}...")
                        
                        # Search for Previous/Next buttons near container
                        try:
                            buttons = self.driver.find_elements(By.XPATH, '//button[contains(text(), "Category") or contains(text(), "Next") or contains(text(), "Previous")]')
                            if len(buttons) >= 2:
                                print(f"   ✓ {len(buttons)} navigation buttons found")
                        except:
                            pass
                        break
                    except:
                        continue
                
                if not playlist_container_xpath:
                    print("   ❌ No playlist container found")
                    print("   💾 Saving HTML for analysis...")
                    with open('../output/html/unknown_structure.html', 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    self.driver.save_screenshot('../output/screenshots/unknown_structure.png')
                    return []
        
        # STEP 2: Search and click load buttons if they exist
        print("\n📂 Looking for additional categories...")
        max_load_clicks = 50
        load_clicks = 0
        
        while load_clicks < max_load_clicks:
            try:
                # Search for text "Load" or similar
                load_buttons = self.driver.find_elements(By.XPATH, '//button[contains(text(), "Load") or contains(text(), "load")]')
                
                if load_buttons:
                    load_next_button = load_buttons[0]
                    if load_next_button.is_displayed() and load_next_button.is_enabled():
                        print(f"   ✓ Clicking load button ({load_clicks + 1})...")
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", load_next_button)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", load_next_button)
                        load_clicks += 1
                        time.sleep(3)
                    else:
                        break
                else:
                    break
            except:
                break
        
        if load_clicks > 0:
            print(f"   ✅ {load_clicks} additional categories loaded")
        else:
            print("   ✓ No additional categories to load")
        print()
        
        # STEP 3: Click "Previous Category" until blocked (go to beginning)
        # CRITICAL FIX: ALWAYS go to Cat 1 first, even with checkpoint
        # This is required because the JavaScript only loads content correctly
        # when you navigate from Cat 1 → Cat 2 → Cat 3, etc.
        print("⏪ Navigating to start with Previous Category...")
        prev_clicks = 0
        max_prev_clicks = 200
        
        while prev_clicks < max_prev_clicks:
            try:
                prev_button = self.driver.find_element(By.XPATH, prev_button_xpath)
                
                if prev_button.is_enabled() and prev_button.is_displayed():
                    print(f"   ⏪ Previous Category ({prev_clicks + 1})...")
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", prev_button)
                    time.sleep(1)
                    self.driver.execute_script("arguments[0].click();", prev_button)
                    prev_clicks += 1
                    time.sleep(4)
                else:
                    print("   ✓ 'Previous Category' disabled - start reached")
                    break
            except NoSuchElementException:
                print("   ✓ 'Previous Category' not found - start reached")
                break
            except Exception as e:
                print(f"   ⚠️  Error: {e}")
                break
        
        print(f"   ✅ Navigated {prev_clicks} categories back\n")
        
        # STEP 4: Navigate with "Next Category" extracting content
        print("▶️  Navigating with Next Category...\n")
        
        category_count = 0
        max_categories = 50
        
        # Navigate to start_category if needed (with proper content loading)
        if start_category > 1:
            print(f"⏩ Fast-forwarding to category {start_category}...")
            for _ in range(start_category - 1):
                try:
                    next_button = self.driver.find_element(By.XPATH, next_button_xpath)
                    if next_button.is_enabled():
                        self.driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(5)  # Wait for content to load properly
                    else:
                        break
                except:
                    break
            category_count = start_category - 1
            print(f"   ✓ Fast-forwarded to category {start_category}\n")
        
        while category_count < max_categories:
            category_count += 1
            
            # Check if we've hit max_lessons limit
            if max_lessons is not None and self.lessons_processed_this_batch >= max_lessons:
                print(f"\n✅ Batch limit reached ({max_lessons} lessons processed)")
                break
            
            print(f"\n📚 Processing CATEGORY #{category_count}...")
            
            # Wait for page to stabilize
            time.sleep(3)
            
            # OPTIMIZATION: Check if this category is already complete by counting files
            course_name = getattr(self, 'current_course_name', 'Unknown').replace('/', '-').replace(' ', '_')
            subfolder = ""
            if course_name.startswith("APEX"):
                subfolder = "APEX/"
            elif course_name.startswith("Hypnosis"):
                subfolder = "Hypnosis/"
            elif course_name.startswith("The_Simple_Course"):
                subfolder = "Simple_Course/"
            
            videos_dir = Path("../output/videos")
            existing_files = list(videos_dir.glob(f"{subfolder}{course_name}_Cat{category_count:02d}_*.mp4"))
            existing_count = len(existing_files)
            
            try:
                # 1. Search for playlist container FIRST
                playlist_container = self.driver.find_element(By.XPATH, playlist_container_xpath)
                print("   ✓ Container found")
                
                # 2. Search for ALL lesson items (with UUID IDs)
                playlist_items = playlist_container.find_elements(
                    By.XPATH, 
                    './/*[@id and string-length(@id) > 30]'
                )
                
                print(f"   ✓ {len(playlist_items)} item(s) found in playlist")
                
                # 3. Track URLs already seen in this category
                seen_urls_in_category = set()
                
                # 4. Click on load-next-post MULTIPLE TIMES to load ALL content
                load_clicks = 0
                max_load_clicks = 20  # Maximum clicks to avoid infinite loops
                while load_clicks < max_load_clicks:
                    try:
                        load_button = self.driver.find_element(By.XPATH, '//*[@id="load-next-post"]/button')
                        if not load_button.is_displayed() or not load_button.is_enabled():
                            break
                        
                        # Count items before click
                        items_before = len(playlist_container.find_elements(
                            By.XPATH, './/*[@id and string-length(@id) > 30]'
                        ))
                        
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_button)
                        time.sleep(1)
                        self.driver.execute_script("arguments[0].click();", load_button)
                        time.sleep(3)
                        load_clicks += 1
                        
                        # Count items after click
                        items_after = len(playlist_container.find_elements(
                            By.XPATH, './/*[@id and string-length(@id) > 30]'
                        ))
                        
                        print(f"   🔘 Load-next-post #{load_clicks}: {items_before} → {items_after} items")
                        
                        # If no more items loaded, exit
                        if items_after == items_before:
                            break
                            
                    except:
                        break  # Doesn't exist or can't be clicked anymore
                
                if load_clicks > 0:
                    print(f"   ✓ Content loaded after {load_clicks} clicks")
                    # Search for ALL items again after loading
                    playlist_items = playlist_container.find_elements(
                        By.XPATH, 
                        './/*[@id and string-length(@id) > 30]'
                    )
                    print(f"   ✓ {len(playlist_items)} total item(s) after loading")
                
                # 4.6 NEW: If no load-next-post button, SCROLL inside container
                # to load lazy-loaded elements (especially for Course #1 with 112 lessons)
                if load_clicks == 0 and len(playlist_items) > 20:
                    print(f"   🔄 Scrolling in container to load {len(playlist_items)} items...")
                    
                    # Scroll multiple times until the end of the container
                    last_height = 0
                    scroll_attempts = 0
                    max_scrolls = 15
                    
                    while scroll_attempts < max_scrolls:
                        # Scroll to the end of the container
                        self.driver.execute_script(
                            "arguments[0].scrollTop = arguments[0].scrollHeight;", 
                            playlist_container
                        )
                        time.sleep(2)
                        
                        # Get current height
                        new_height = self.driver.execute_script(
                            "return arguments[0].scrollHeight;", 
                            playlist_container
                        )
                        
                        scroll_attempts += 1
                        
                        # If height didn't change, everything is loaded
                        if new_height == last_height:
                            break
                        
                        last_height = new_height
                        print(f"   📜 Scroll #{scroll_attempts}: height {new_height}px")
                    
                    print(f"   ✓ Scroll completed after {scroll_attempts} attempts")
                    
                    # Search for ALL items again after scroll
                    playlist_items = playlist_container.find_elements(
                        By.XPATH, 
                        './/*[@id and string-length(@id) > 30]'
                    )
                    print(f"   ✓ {len(playlist_items)} total item(s) after scroll")
                
                # 5. NOW read the lesson counter AFTER all content is loaded
                try:
                    lesson_counter = self.driver.find_element(By.XPATH, '//*[@id="playlist-wrapper"]/div[1]/div/div/p')
                    counter_text = lesson_counter.text  # Format: "Lesson 1 of 8" or "112 Lessons"
                    print(f"   📊 Counter text: '{counter_text}'")
                    
                    # Extract total lesson number
                    import re
                    # Try different formats
                    match = re.search(r'of (\d+)', counter_text)  # "Lesson 1 of 8"
                    if not match:
                        match = re.search(r'(\d+)\s+Lesson', counter_text)  # "112 Lessons"
                    
                    if match:
                        total_lessons_in_category = int(match.group(1))
                        print(f"   📊 Extracted total: {total_lessons_in_category} lessons")
                    else:
                        total_lessons_in_category = len(playlist_items)  # Use actual count
                        print(f"   ⚠️  Could not parse counter, using item count: {total_lessons_in_category}")
                except Exception as e:
                    total_lessons_in_category = len(playlist_items)  # Use actual count if counter not found
                    print(f"   ⚠️  Could not read counter ({e}), using item count: {total_lessons_in_category} lessons")
                
                # Check if category is already complete NOW
                if existing_count >= total_lessons_in_category and total_lessons_in_category > 0:
                    print(f"   ✅ Category complete: {existing_count}/{total_lessons_in_category} videos already downloaded")
                    print(f"   ⏭️  Skipping to next category...\n")
                    
                    # Advance to next category
                    try:
                        next_button = self.driver.find_element(By.XPATH, next_button_xpath)
                        if next_button.is_enabled() and next_button.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", next_button)
                            time.sleep(6)
                            continue  # Skip to next category iteration
                        else:
                            print("   ✓ 'Next Category' disabled - end of course reached")
                            break
                    except:
                        print("   ✓ Could not advance - end of course reached")
                        break
                elif existing_count > 0:
                    print(f"   📁 Already have {existing_count}/{total_lessons_in_category} videos in this category")
                    
                    # OPTIMIZATION: Find first missing lesson and scroll directly to it
                    # Check which lesson numbers are missing
                    existing_lesson_numbers = set()
                    for file in existing_files:
                        # Extract lesson number from filename like "APEX_Cat03_Lesson78.mp4"
                        match = re.search(r'Lesson(\d+)\.mp4$', file.name)
                        if match:
                            existing_lesson_numbers.add(int(match.group(1)))
                    
                    # Find first missing lesson number
                    first_missing = None
                    for lesson_num in range(1, total_lessons_in_category + 1):
                        if lesson_num not in existing_lesson_numbers:
                            first_missing = lesson_num
                            break
                    
                    if first_missing and first_missing > 1:
                        print(f"   🎯 First missing lesson: #{first_missing}")
                        print(f"   🔍 Searching for lesson with number {first_missing}...")
                        
                        # Find the item with matching lesson number using cat-lesson-title
                        try:
                            # Search for div with class "cat-lesson-title" containing the lesson number
                            target_item = None
                            for item in playlist_items:
                                try:
                                    # Look for the lesson title div inside this item
                                    title_divs = item.find_elements(By.XPATH, './/div[contains(@class, "cat-lesson-title")]')
                                    for title_div in title_divs:
                                        if title_div.text.strip() == str(first_missing):
                                            target_item = item
                                            break
                                    if target_item:
                                        break
                                except:
                                    continue
                            
                            if target_item:
                                print(f"   ✓ Found lesson #{first_missing} in DOM")
                                print(f"   📜 Scrolling directly to lesson #{first_missing}...")
                                
                                # Scroll to this item in the container
                                self.driver.execute_script("""
                                    var container = arguments[0];
                                    var item = arguments[1];
                                    var itemTop = item.offsetTop;
                                    var containerHeight = container.clientHeight;
                                    container.scrollTop = itemTop - 100;
                                """, playlist_container, target_item)
                                time.sleep(2)
                                print(f"   ✓ Scrolled to lesson #{first_missing}")
                            else:
                                print(f"   ⚠️  Could not find lesson #{first_missing} in DOM")
                        except Exception as e:
                            print(f"   ⚠️  Error scrolling to lesson: {e}")
                
                # 6. NEW OPTIMIZED APPROACH: Find all lessons with cat-lesson-title and process only missing ones
                print(f"   🔍 Scanning lessons using cat-lesson-title...")
                
                # Find all lesson items with cat-lesson-title
                lesson_items_map = {}  # lesson_number -> item element
                try:
                    all_lesson_divs = playlist_container.find_elements(By.XPATH, './/div[contains(@class, "cat-lesson-title")]')
                    print(f"   ✓ Found {len(all_lesson_divs)} lessons with cat-lesson-title")
                    
                    for lesson_div in all_lesson_divs:
                        try:
                            lesson_text = lesson_div.text.strip()
                            if lesson_text.isdigit():
                                lesson_num = int(lesson_text)
                                # Find the parent clickable item (go up the DOM tree)
                                parent = lesson_div.find_element(By.XPATH, './ancestor::*[@id and string-length(@id) > 30][1]')
                                lesson_items_map[lesson_num] = parent
                        except:
                            continue
                    
                    print(f"   ✓ Mapped {len(lesson_items_map)} lessons")
                except Exception as e:
                    print(f"   ⚠️  Could not map lessons: {e}")
                    print(f"   🔄 Falling back to old iteration method...")
                    lesson_items_map = {}
                
                # Determine which lessons to process
                lessons_to_process = []
                if lesson_items_map:
                    # NEW METHOD: Only process missing lessons
                    for lesson_num in sorted(lesson_items_map.keys()):
                        # Check if file exists
                        expected_filename = f"{course_name}_Cat{category_count:02d}_Lesson{lesson_num:02d}.mp4"
                        expected_path = videos_dir / subfolder / expected_filename
                        
                        if not expected_path.exists():
                            lessons_to_process.append(lesson_num)
                    
                    print(f"   📋 Lessons to process: {len(lessons_to_process)} missing")
                    if lessons_to_process[:10]:
                        print(f"      First 10: {lessons_to_process[:10]}")
                else:
                    # OLD METHOD: Process all items
                    print(f"   🔄 Using old method: processing all {len(playlist_items)} items")
                    lessons_to_process = list(range(1, total_lessons_in_category + 1))
                
                # Process lessons
                lessons_processed = 0
                lessons_with_content = 0
                lesson_urls = []
                lessons_actually_checked = 0
                
                for lesson_num_to_process in lessons_to_process:
                    # Check batch limit
                    if max_lessons is not None and self.lessons_processed_this_batch >= max_lessons:
                        print(f"      ✅ Batch limit reached, stopping at lesson {lessons_processed}")
                        break
                    
                    # Get the item element for this lesson number
                    if lesson_items_map:
                        # NEW METHOD: Get item directly from map
                        if lesson_num_to_process not in lesson_items_map:
                            print(f"      ⚠️  Lesson #{lesson_num_to_process} not in map, skipping")
                            continue
                        item = lesson_items_map[lesson_num_to_process]
                        lesson_number_in_dom = lesson_num_to_process
                    else:
                        # OLD METHOD: Iterate through playlist_items (fallback)
                        if lesson_num_to_process > len(playlist_items):
                            break
                        item = playlist_items[lesson_num_to_process - 1]
                        lesson_number_in_dom = lesson_num_to_process
                    
                    # From here on, we're actually checking/processing this lesson
                    lessons_actually_checked += 1
                    
                    try:
                        item_id = item.get_attribute('id')
                        
                        # Filter elements that are definitely NOT content items
                        skip_ids = ['playlist-wrapper', 'post-playlist', 'plyr-video', 'post-audio', 
                                   'product-list', 'app', 'app-container', 'navbar', 'navigation', 'app-launch']
                        if any(skip_id in item_id for skip_id in skip_ids):
                            continue
                        
                        # IMPORTANT: Scroll FIRST so the element is visible
                        # Don't check is_displayed() before scroll because it may be outside viewport
                        try:
                            # Scroll inside playlist container to make element visible
                            self.driver.execute_script("""
                                var container = arguments[0];
                                var item = arguments[1];
                                var itemTop = item.offsetTop;
                                var containerHeight = container.clientHeight;
                                container.scrollTop = itemTop - (containerHeight / 2);
                            """, playlist_container, item)
                            time.sleep(0.5)
                        except:
                            pass
                        
                        # Now check if visible after scroll
                        if not item.is_displayed():
                            continue
                        
                        # Verificar que sea un elemento clickeable
                        try:
                            tag = item.tag_name
                            if tag not in ['div', 'button', 'a', 'li']:
                                continue
                        except:
                            continue
                        
                        # Display lesson number (use DOM number if available, otherwise use counter)
                        display_lesson_num = lesson_number_in_dom if lesson_number_in_dom else (lessons_processed + 1)
                        print(f"      🎯 Lesson #{display_lesson_num} (ID: {item_id[:36]})")
                        
                        # Scroll to element
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                        time.sleep(1)
                        
                        # CRITICAL: Click on correct element according to structure
                        click_success = False
                        
                        # Strategy depends on detected structure
                        if structure_type == "post-playlist":
                            # post-playlist: Search for <a> or <button> inside the item
                            try:
                                clickable_elements = item.find_elements(By.XPATH, './/a | .//button')
                                if clickable_elements:
                                    clickable = clickable_elements[0]
                                    self.driver.execute_script("arguments[0].click();", clickable)
                                    lessons_processed += 1
                                    click_success = True
                                else:
                                    raise Exception("No <a>/<button> en post-playlist")
                            except Exception as e:
                                print(f"         ⚠️  post-playlist: {str(e)[:40]}")
                                # Fallback: direct click
                                try:
                                    self.driver.execute_script("arguments[0].click();", item)
                                    lessons_processed += 1
                                    click_success = True
                                except Exception as e2:
                                    print(f"         ❌ Could not click: {str(e2)[:60]}")
                                    continue
                        else:
                            # playlist-wrapper: Try child div first (original method)
                            try:
                                clickable_div = self.driver.find_element(By.XPATH, f'//*[@id="{item_id}"]/div')
                                self.driver.execute_script("arguments[0].click();", clickable_div)
                                lessons_processed += 1
                                click_success = True
                            except:
                                # Fallback: direct click on item
                                try:
                                    self.driver.execute_script("arguments[0].click();", item)
                                    lessons_processed += 1
                                    click_success = True
                                except:
                                    try:
                                        item.click()
                                        lessons_processed += 1
                                        click_success = True
                                    except Exception as e:
                                        print(f"         ❌ No se pudo hacer click: {str(e)[:60]}")
                                        continue
                        
                        if not click_success:
                            print(f"         ❌ Could not click on lesson, skipping...")
                            continue
                        
                        # Esperar a que cargue el contenido
                        print(f"         ⏳ Waiting for video to load...")
                        time.sleep(3)
                        
                        # Check if URL changed (indicates navigation to lesson)
                        current_url = self.driver.current_url
                        print(f"         🌐 URL: {current_url[-60:]}")
                        
                        # Esperar a que el video se precargue (sin reproducir)
                        print(f"         ⏳ Waiting for video preload (10s)...")
                        time.sleep(10)
                        
                        # Try to play to force full HLS load (optional)
                        video_played = False
                        try:
                            # Search and play if available
                            play_result = self.driver.execute_script("""
                                // Try with Plyr button
                                var playBtn = document.querySelector('.plyr__control[data-plyr="play"]') ||
                                             document.querySelector('button[data-plyr="play"]');
                                if (playBtn) {
                                    playBtn.click();
                                    return 'plyr';
                                }
                                
                                // Try with video tag
                                var vid = document.querySelector('video');
                                if (vid) {
                                    vid.play();
                                    return 'video';
                                }
                                
                                return 'none';
                            """)
                            
                            if play_result in ['plyr', 'video']:
                                print(f"         ▶️  Playback started ({play_result})")
                                time.sleep(8)  # Esperar carga del HLS
                                
                                # 🚀 CAPTURE FROM DOM IMMEDIATELY (headless-compatible)
                                try:
                                    dom_urls = self.extract_video_from_dom()
                                    output_file = os.path.join(LOGS_DIR, 'all_m3u8_urls.txt')
                                    metadata_file = os.path.join(LOGS_DIR, 'video_metadata.jsonl')
                                    
                                    # CRITICAL: Only capture THE FIRST new URL for THIS lesson
                                    captured_this_lesson = 0
                                    for url in dom_urls:
                                        if captured_this_lesson > 0:
                                            break  # Only capture 1 URL per lesson
                                            
                                        if 'master.m3u8' in url and 'token=' in url:
                                            # Build expected filename
                                            course_name = getattr(self, 'current_course_name', 'Unknown').replace('/', '-').replace(' ', '_')
                                            # Use lesson_number_in_dom if available, otherwise lessons_processed
                                            actual_lesson_num = lesson_number_in_dom if lesson_number_in_dom else lessons_processed
                                            filename = f"{course_name}_Cat{category_count:02d}_Lesson{actual_lesson_num:02d}.mp4"
                                            
                                            # Determine subfolder based on course name
                                            subfolder = ""
                                            if course_name.startswith("APEX"):
                                                subfolder = "APEX/"
                                            elif course_name.startswith("Hypnosis"):
                                                subfolder = "Hypnosis/"
                                            elif course_name.startswith("The_Simple_Course"):
                                                subfolder = "Simple_Course/"
                                            
                                            filepath = Path(f"../output/videos/{subfolder}{filename}")
                                            
                                            # Check if file already exists with valid size
                                            if filepath.exists():
                                                file_size = filepath.stat().st_size
                                                if file_size > 1048576:  # > 1MB = valid
                                                    print(f"         ℹ️  Already downloaded: {filename} ({file_size / (1024*1024):.1f}MB) - SKIPPING")
                                                    # DON'T count skipped videos in batch limit
                                                    # Just update position tracking
                                                    self.last_category_processed = category_count
                                                    self.last_lesson_processed = actual_lesson_num
                                                    captured_this_lesson += 1
                                                    continue
                                                else:
                                                    print(f"         ⚠️  File exists but too small ({file_size:,} bytes) - RE-DOWNLOADING")
                                            
                                            # File doesn't exist or is invalid - proceed with download
                                            if url not in seen_urls_in_category:
                                                seen_urls_in_category.add(url)
                                                
                                                # Extract video_id for tracking
                                                video_id = url.split('/videos/')[-1].split('_')[0] if '/videos/' in url else url.split('/')[-1][:36]
                                                self.captured_video_ids.add(video_id)
                                                
                                                # WRITE IMMEDIATELY
                                                with open(output_file, 'a', encoding='utf-8') as f:
                                                    f.write(f"{url}\n")
                                                    f.flush()
                                                
                                                import json
                                                with open(metadata_file, 'a', encoding='utf-8') as f:
                                                    metadata = {
                                                        'url': url,
                                                        'course': getattr(self, 'current_course_name', 'Unknown'),
                                                        'category': category_count,
                                                        'lesson': actual_lesson_num
                                                    }
                                                    f.write(json.dumps(metadata, ensure_ascii=False) + '\n')
                                                    f.flush()
                                                
                                                print(f"         🚀 URL captured → download starting NOW")
                                                
                                                # Download immediately with Selenium session
                                                self.download_video_with_selenium_session(url, filename)
                                                
                                                lesson_urls.append({'url': url, 'type': 'video', 'video_id': video_id})
                                                captured_this_lesson += 1
                                                self.lessons_processed_this_batch += 1
                                                # Update last position
                                                self.last_category_processed = category_count
                                                self.last_lesson_processed = actual_lesson_num
                                    
                                    if captured_this_lesson > 0:
                                        print(f"         ✅ Captured URL for this lesson")
                                    elif dom_urls:
                                        print(f"         ℹ️  Found {len(dom_urls)} URLs but all already captured")
                                    else:
                                        print(f"         ⚠️  No URLs found in DOM")
                                except Exception as ex:
                                    print(f"         ❌ DOM extraction error: {str(ex)[:40]}")
                                
                                # Pausar
                                self.driver.execute_script("""
                                    var playBtn = document.querySelector('.plyr__control[data-plyr="play"]');
                                    if (playBtn) playBtn.click();
                                    var vid = document.querySelector('video');
                                    if (vid) vid.pause();
                                """)
                                video_played = True
                            else:
                                print(f"         ℹ️  No play button (video may be preloaded)")
                                time.sleep(5)
                                
                        except Exception as e:
                            print(f"         ℹ️  Capturing without playback")
                            time.sleep(5)
                        
                        # lesson_urls ya tiene las URLs capturadas después del playback
                        
                        if lesson_urls:
                            videos = [u for u in lesson_urls if u['type'] == 'video']
                            audios = [u for u in lesson_urls if u['type'] == 'audio']
                            
                            if videos or audios:
                                print(f"         ✅ {len(videos)} video(s) + {len(audios)} audio(s)")
                                all_videos_urls.extend(lesson_urls)
                                lessons_with_content += 1
                        
                    except Exception as e:
                        if 'stale element' not in str(e).lower():
                            print(f"         ⚠️  Error: {str(e)[:50]}")
                        continue
                
                if lessons_with_content > 0:
                    print(f"   ✅ Lessons with content: {lessons_with_content}/{lessons_processed}")
                else:
                    # OLD METHOD DISABLED - only use individual lesson capture with metadata
                    print(f"   ⚠️  No videos captured in this category (no playback detected)")
                    # Note: This happens when videos don't have play button
                    # Videos are still captured individually if they loaded
                
                # 5. Save screenshot of current category
                self.driver.save_screenshot(f'../output/screenshots/course_{course_index}_category_{category_count}.png')
                
                # 6. Click on "Next Category" to advance to the next one
                # IMPORTANT: Only advance if we finished all lessons in current category
                # If batch limit was reached mid-category, DON'T advance
                should_advance_category = True
                
                # Check if we stopped mid-category due to batch limit
                if max_lessons is not None and self.lessons_processed_this_batch >= max_lessons:
                    # Calculate how many lessons remain in this category
                    remaining_in_category = total_lessons_in_category - lessons_processed
                    
                    if remaining_in_category > 0:
                        should_advance_category = False
                        print(f"   ⏸️  Staying in category {category_count} ({remaining_in_category} lessons remaining)")
                    else:
                        print(f"   ✅ Category {category_count} completed (all {total_lessons_in_category} lessons processed)")
                
                if not should_advance_category:
                    # Don't click Next Category, just break to return control
                    print(f"\n✅ Batch limit reached ({max_lessons} lessons processed)")
                    break
                
                print("\n   🔄 Advancing to next category...")
                
                try:
                    # Re-search for button to avoid stale element
                    next_button = self.driver.find_element(By.XPATH, next_button_xpath)
                    
                    # Check if button is enabled
                    is_enabled = next_button.is_enabled()
                    is_displayed = next_button.is_displayed()
                    
                    print(f"   Next Category - Enabled: {is_enabled}, Visible: {is_displayed}")
                    
                    if not is_enabled or not is_displayed:
                        print("   ✓ 'Next Category' disabled - end of course reached")
                        break
                    
                    # Check Previous Category as well
                    try:
                        prev_button = self.driver.find_element(By.XPATH, prev_button_xpath)
                        prev_enabled = prev_button.is_enabled()
                        print(f"   Previous Category - Enabled: {prev_enabled}")
                    except:
                        pass
                    
                    # Save current URL before clicking
                    current_url = self.driver.current_url
                    
                    # Scroll to the button
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    time.sleep(1)
                    
                    # Click using JavaScript to avoid stale element
                    print("   ➡️  Next Category...")
                    self.driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(6)
                    
                    # Wait for content to change
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, playlist_container_xpath))
                        )
                    except:
                        print("   ⚠️  Timeout waiting for new category, continuing...")
                    
                    # Check if URL changed (redirect to another page)
                    new_url = self.driver.current_url
                    if new_url != current_url and 'course' not in new_url:
                        print(f"   ⚠️  Redirected out of course: {new_url}")
                        print("   ✓ End of course reached")
                        break
                    
                except NoSuchElementException:
                    print("   ✓ 'Next Category' not found - end of course reached")
                    break
                except Exception as e:
                    # If stale element error, continue with next category
                    if 'stale element' in str(e).lower():
                        print(f"   ⚠️  Stale element error - continuing...")
                        time.sleep(3)
                        continue
                    else:
                        print(f"   ⚠️  Error with 'Next Category': {e}")
                        # Try once more before breaking
                        print("   🔄 Retrying once more...")
                        time.sleep(5)
                        try:
                            next_button_retry = self.driver.find_element(By.XPATH, next_button_xpath)
                            if next_button_retry.is_enabled():
                                self.driver.execute_script("arguments[0].click();", next_button_retry)
                                time.sleep(6)
                                continue
                        except:
                            pass
                        break
                
            except NoSuchElementException as e:
                print(f"   ⚠️  Playlist container not found")
                print(f"   ✓ End of course reached (category {category_count})")
                break
            except Exception as e:
                print(f"   ❌ Error processing category: {e}")
                break
        
        if category_count >= max_categories:
            print(f"\n   ⚠️  Reached limit of {max_categories} categories")
        
        print(f"\n   ✅ Total categories processed: {category_count}")
        print(f"   ✅ Total URLs captured: {len(all_videos_urls)}")
        
        # Save final page
        with open('../output/html/course_final_page.html', 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)
        self.driver.save_screenshot('../output/screenshots/course_final_page.png')
        
        print(f"\n   📹 Total: {len(all_videos_urls)} unique videos found")
        print(f"   📍 Last position: Cat {self.last_category_processed}, Lesson {self.last_lesson_processed + 1}")
        
        return all_videos_urls, self.last_category_processed, self.last_lesson_processed
    
    def extract_video_id(self, url):
        """Extract unique video ID from URL"""
        try:
            if '/videos/' in url:
                return url.split('/videos/')[-1].split('_')[0]
            elif 'master.m3u8' in url:
                # Extract from path before master.m3u8
                parts = url.split('/')
                for part in reversed(parts):
                    if len(part) > 30 and '-' in part:
                        return part.split('?')[0]
            # For audio or others
            return url.split('/')[-1].split('?')[0][:36]
        except:
            return url[:36]
    
    def get_network_logs(self):
        """Capture video and audio URLs from network logs - only master.m3u8 and audio files NOT previously captured"""
        
        media_urls = []
        
        try:
            logs = self.driver.get_log('performance')
            
            for entry in logs:
                try:
                    log = json.loads(entry['message'])['message']
                    
                    if log['method'] == 'Network.responseReceived':
                        url = log['params']['response']['url']
                        mime_type = log['params']['response'].get('mimeType', '')
                        
                        # Capture master.m3u8 (videos)
                        if 'master.m3u8' in url and 'token=' in url:
                            video_id = url.split('/videos/')[-1].split('_')[0] if '/videos/' in url else url.split('/')[-1][:36]
                            
                            # Only add if NOT captured before
                            if video_id not in self.captured_video_ids:
                                self.captured_video_ids.add(video_id)
                                media_urls.append({
                                    'url': url,
                                    'type': 'video',
                                    'video_id': video_id
                                })
                        
                        # Capture audio files (mp3, m4a, aac, etc)
                        elif any(ext in url.lower() for ext in ['.mp3', '.m4a', '.aac', '.wav', '.ogg']) or 'audio' in mime_type:
                            # Verify it's from content.apisystem.tech or similar
                            if 'content.apisystem.tech' in url or 'assetsdrm' in url or 'cdn.courses' in url:
                                audio_id = url.split('/')[-1].split('?')[0]
                                
                                # Only add if NOT captured before
                                if audio_id not in self.captured_video_ids:
                                    self.captured_video_ids.add(audio_id)
                                    media_urls.append({
                                        'url': url,
                                        'type': 'audio',
                                        'video_id': audio_id
                                    })
                
                except:
                    continue
        
        except Exception as e:
            print(f"   ⚠️  Error analyzing logs: {e}")
        
        return media_urls
    
    def extract_video_from_dom(self):
        """Extract video URLs directly from DOM/HTML and performance logs - improved version"""
        video_urls = []
        
        try:
            # METHOD 1: Capture ALL network logs - Search for .m3u8 in ENTIRE timeline
            all_logs = []
            try:
                logs = self.driver.get_log('performance')
                all_logs.extend(logs)
            except:
                pass
            
            for log in all_logs:
                try:
                    message = json.loads(log['message'])
                    method = message['message']['method']
                    
                    # Search in ALL network responses
                    if method == 'Network.responseReceived':
                        response = message['message']['params']['response']
                        url = response.get('url', '')
                        
                        # Capturar CUALQUIER .m3u8
                        if '.m3u8' in url:
                            video_urls.append(url)
                        
                        # Capture audio
                        if any(ext in url for ext in ['.mp3', '.m4a', '.aac', '.wav']):
                            if 'content.apisystem' in url or 'cdn.courses' in url or 'assetsdrm' in url:
                                video_urls.append(url)
                    
                    # Also search in requestWillBeSent (outgoing requests)
                    elif method == 'Network.requestWillBeSent':
                        request = message['message']['params']['request']
                        url = request.get('url', '')
                        
                        if '.m3u8' in url:
                            video_urls.append(url)
                
                except:
                    continue
            
            # METHOD 2: Execute JavaScript to search in Plyr player
            try:
                plyr_sources = self.driver.execute_script("""
                    var sources = [];
                    
                    // Method 1: Search in Plyr player
                    var videos = document.querySelectorAll('video');
                    videos.forEach(function(video) {
                        // currentSrc (may be blob, but we try)
                        if (video.currentSrc && !video.currentSrc.startsWith('blob:')) {
                            sources.push(video.currentSrc);
                        }
                        
                        // src attribute
                        if (video.src && !video.src.startsWith('blob:')) {
                            sources.push(video.src);
                        }
                        
                        // source elements
                        var sourceTags = video.querySelectorAll('source');
                        sourceTags.forEach(function(s) {
                            if (s.src && !s.src.startsWith('blob:')) {
                                sources.push(s.src);
                            }
                        });
                    });
                    
                    // Method 2: Search in window.Plyr if exists
                    if (typeof window.plyr !== 'undefined' && window.plyr.source) {
                        if (window.plyr.source.sources) {
                            window.plyr.source.sources.forEach(function(s) {
                                if (s.src) sources.push(s.src);
                            });
                        }
                    }
                    
                    // Method 3: Search in Hls.js if loaded
                    if (typeof Hls !== 'undefined' && Hls.DefaultConfig) {
                        // Try to find Hls instances
                        for (var prop in window) {
                            try {
                                if (window[prop] && window[prop].url) {
                                    sources.push(window[prop].url);
                                }
                            } catch(e) {}
                        }
                    }
                    
                    return sources;
                """)
                video_urls.extend(plyr_sources)
            except Exception as e:
                print(f"      ⚠️  Error in JavaScript: {e}")
            
            # METHOD 3: Search in localStorage/sessionStorage
            try:
                storage_urls = self.driver.execute_script("""
                    var urls = [];
                    
                    // localStorage
                    for (var i = 0; i < localStorage.length; i++) {
                        var key = localStorage.key(i);
                        var value = localStorage.getItem(key);
                        if (value && value.includes('.m3u8')) {
                            var matches = value.match(/https?:\\/\\/[^\\s"']+\\.m3u8[^\\s"']*/g);
                            if (matches) urls = urls.concat(matches);
                        }
                    }
                    
                    // sessionStorage
                    for (var i = 0; i < sessionStorage.length; i++) {
                        var key = sessionStorage.key(i);
                        var value = sessionStorage.getItem(key);
                        if (value && value.includes('.m3u8')) {
                            var matches = value.match(/https?:\\/\\/[^\\s"']+\\.m3u8[^\\s"']*/g);
                            if (matches) urls = urls.concat(matches);
                        }
                    }
                    
                    return urls;
                """)
                video_urls.extend(storage_urls)
            except:
                pass
            
            # Remove duplicates, filter blobs, and prioritize master.m3u8
            unique_urls = []
            seen = set()
            
            for url in video_urls:
                # Clean
                url = str(url).split('"')[0].split("'")[0].split('<')[0].split('>')[0].strip()
                
                # Filter
                if not url or url.startswith('blob:') or url.startswith('data:'):
                    continue
                
                if url in seen:
                    continue
                
                # Only valid URLs
                if '.m3u8' in url or any(ext in url for ext in ['.mp3', '.m4a', '.aac']):
                    seen.add(url)
                    
                    # Prioritize master.m3u8
                    if 'master.m3u8' in url:
                        unique_urls.insert(0, url)
                    else:
                        unique_urls.append(url)
            
            return unique_urls
            
        except Exception as e:
            print(f"      ⚠️  Error extrayendo del DOM: {e}")
            return []
    
    def analyze_video(self, video_url):
        """Analyze a video page to get the download URL"""
        print(f"\n🎬 Analyzing video: {video_url}")
        
        try:
            self.driver.get(video_url)
            time.sleep(5)
            
            self.driver.save_screenshot('../output/screenshots/video_page.png')
            
            # Save HTML
            with open('video_page_full.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            
            # Search for video elements
            video_sources = []
            
            # 1. Tags de video directo
            video_tags = self.driver.find_elements(By.TAG_NAME, 'video')
            for video in video_tags:
                src = video.get_attribute('src')
                if src:
                    video_sources.append({
                        'url': src,
                        'type': 'video_tag',
                        'quality': 'default'
                    })
                
                # Sources inside video
                sources = video.find_elements(By.TAG_NAME, 'source')
                for source in sources:
                    src = source.get_attribute('src')
                    if src:
                        video_sources.append({
                            'url': src,
                            'type': 'video_source',
                            'quality': source.get_attribute('label') or 'unknown'
                        })
            
            # 2. Iframes
            iframes = self.driver.find_elements(By.TAG_NAME, 'iframe')
            for iframe in iframes:
                src = iframe.get_attribute('src')
                if src and ('video' in src or 'vimeo' in src or 'wistia' in src):
                    video_sources.append({
                        'url': src,
                        'type': 'iframe',
                        'quality': 'embedded'
                    })
            
            # 3. Search in Network requests (if possible)
            # This would require additional configuration with Chrome DevTools Protocol
            
            # 4. Search in page JavaScript code
            page_source = self.driver.page_source
            
            # Search for video URLs in HTML/JS
            video_url_patterns = [
                r'https?://[^\s<>"\']+\.mp4',
                r'https?://[^\s<>"\']+\.m3u8',
                r'https?://[^\s<>"\']+\.webm',
                r'https?://player\.vimeo\.com/video/\d+',
                r'https?://.*wistia\.com/.*',
            ]
            
            for pattern in video_url_patterns:
                matches = re.findall(pattern, page_source)
                for match in matches:
                    # Clean the URL
                    match = match.split('"')[0].split("'")[0].split('\\')[0]
                    video_sources.append({
                        'url': match,
                        'type': 'regex_match',
                        'quality': 'found_in_source'
                    })
            
            # Remove duplicates
            unique_sources = []
            seen = set()
            for source in video_sources:
                if source['url'] not in seen:
                    seen.add(source['url'])
                    unique_sources.append(source)
            
            print(f"   📹 {len(unique_sources)} sources found:")
            for i, source in enumerate(unique_sources, 1):
                print(f"   {i}. [{source['type']}] {source['url'][:100]}")
            
            return unique_sources
            
        except Exception as e:
            print(f"❌ Error analyzing video: {e}")
            return []
    
    def download_video(self, video_url, filename):
        """Download a video using requests"""
        print(f"\n⬇️  Downloading: {filename}")
        
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        try:
            # Get cookies from browser for session
            cookies = self.driver.get_cookies()
            session = requests.Session()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'])
            
            response = session.get(video_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(filepath, 'wb') as f:
                if total_size:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            percent = (downloaded / total_size) * 100
                            print(f"\r   Progreso: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='')
                    print()
                else:
                    f.write(response.content)
            
            file_size = os.path.getsize(filepath)
            print(f"✅ Downloaded: {filepath} ({file_size:,} bytes)")
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def run(self):
        """Execute the complete process for multiple courses with batch system"""
        print("=" * 70)
        print("🎬 VIDEO DOWNLOADER - MARC ZELL KLEIN (SELENIUM + BATCH SYSTEM)")
        print("=" * 70)
        
        all_m3u8_urls = []
        processed_courses = []
        
        try:
            # 1. Login (only once)
            if not self.login():
                print("\n❌ Could not complete login")
                print("Check the screenshots and generated HTML files")
                return
            
            # 2. Go to courses page and detect all available courses
            print("\n📚 Detecting available courses...")
            self.driver.get(COURSE_URL)
            time.sleep(3)
            
            # Search for all course cards dynamically
            course_cards = self.driver.find_elements(By.XPATH, '//*[@id="product-list"]/div')
            num_courses = len(course_cards)
            
            print(f"   ✓ {num_courses} courses found")
            
            # Create dynamic course list
            courses = []
            for i in range(1, num_courses + 1):
                courses.append({
                    'index': i,
                    'xpath': f'//*[@id="product-list"]/div[{i}]',
                    'name': f'Course {i}'
                })
            
            # Apply course filter if specified
            if self.course_filter:
                courses = [c for c in courses if c['index'] in self.course_filter]
                if not courses:
                    print(f"   ⚠️  No courses found with specified indices: {self.course_filter}")
                    return
            
            print(f"   📋 Will process {len(courses)} course(s)")
            print(f"   🎯 Batch size: {self.batch_size} lessons per batch")
            print(f"   🔄 Browser restart: Every {self.batch_size} lessons\n")
            
            # Load checkpoint to resume if needed
            checkpoint = self.load_checkpoint()
            start_course_index = checkpoint.get('course_index', 0) if checkpoint else 0
            
            # 3. Process each course with batch system
            for course in courses:
                # Check if course should be skipped based on checkpoint
                if course['index'] - 1 < start_course_index:
                    # Verify if course is actually complete by counting downloaded files
                    course_name_pattern = None
                    if course['index'] == 1:
                        course_name_pattern = "APEX_"
                    elif course['index'] == 2:
                        course_name_pattern = "Hypnosis_"
                    elif course['index'] == 3:
                        course_name_pattern = "The_Simple_Course_"
                    
                    if course_name_pattern:
                        from pathlib import Path
                        videos_dir = Path("../output/videos")
                        # Search in both root and subfolders
                        downloaded_count = len(list(videos_dir.glob(f"{course_name_pattern}*.mp4"))) + \
                                         len(list(videos_dir.glob(f"*/{course_name_pattern}*.mp4")))
                        
                        # Known course sizes (approximate)
                        expected_counts = {
                            1: 112,  # APEX has ~112 lessons
                            2: 50,   # Hypnosis has ~50 lessons (estimate)
                            3: 5     # Simple Course has 5 lessons
                        }
                        
                        expected = expected_counts.get(course['index'], 0)
                        if downloaded_count < expected:
                            print(f"⚠️  Course #{course['index']}: Only {downloaded_count}/{expected} videos downloaded")
                            print(f"   🔄 Removing checkpoint to re-process incomplete course...")
                            if self.checkpoint_file.exists():
                                self.checkpoint_file.unlink()
                            # Don't skip this course
                        else:
                            print(f"✅ Course #{course['index']}: Complete ({downloaded_count}/{expected} videos)")
                            print(f"⏭️  Skipping Course #{course['index']} (already completed)")
                            continue
                    else:
                        print(f"⏭️  Skipping Course #{course['index']} (already completed)")
                        continue
                
                print("\n" + "=" * 70)
                print(f"📚 PROCESSING COURSE #{course['index']} of {len(courses)}")
                print("=" * 70)
                
                # Navigate to course
                success, course_title = self.navigate_to_course(course['index'], course['xpath'])
                
                if not success:
                    print(f"⚠️  Could not navigate to course #{course['index']}, continuing with next...")
                    # Return to course page for the next one
                    print(f"   🔄 Returning to course list...")
                    self.driver.get(COURSE_URL)
                    time.sleep(3)
                    continue
                
                # Update course name
                course['name'] = course_title or course['name']
                course_url = self.driver.current_url
                
                # 4. Process course in batches
                print(f"\n🎬 Processing '{course['name']}' in batches...")
                self.process_course_in_batches(
                    course_index=course['index'] - 1,
                    course_url=course_url,
                    course_name=course['name']
                )
                
                print(f"\n✅ Course '{course['name']}' completed!")
                
                # 5. Return to course page to process the next one
                if course['index'] < len(courses):
                    print(f"\n🔄 Returning to course list to process next...")
                    self.driver.get(COURSE_URL)
                    time.sleep(4)  # Wait for course list to load
                    
                    # Verify we're on the correct page
                    if 'library-v2' in self.driver.current_url:
                        print("   ✓ Back in course list")
                    elif 'login' in self.driver.current_url:
                        print(f"   ⚠️  Session expired, re-logging in...")
                        if self.login():
                            print("   ✓ Re-login successful")
                            # Navigate to course list again
                            self.driver.get(COURSE_URL)
                            time.sleep(4)
                            if 'library-v2' in self.driver.current_url:
                                print("   ✓ Back in course list")
                            else:
                                print(f"   ❌ Still can't access course list: {self.driver.current_url}")
                        else:
                            print("   ❌ Re-login failed")
                    else:
                        print(f"   ⚠️  Unexpected URL: {self.driver.current_url}")
                else:
                    print(f"\n✅ Last course processed - no need to return")
            
            # 6. Save cookies for use with yt-dlp (once at the end)
            print("\n" + "=" * 70)
            print("💾 SAVING DATA")
            print("=" * 70)
            
            print("\n🍪 Saving session cookies...")
            cookies = self.driver.get_cookies()
            with open('../output/logs/cookies.json', 'w') as f:
                json.dump(cookies, f, indent=2)
            
            # Also in Netscape format for yt-dlp
            with open('../output/logs/cookies.txt', 'w') as f:
                f.write("# Netscape HTTP Cookie File\n")
                for cookie in cookies:
                    f.write(f"{cookie.get('domain', '')}\tTRUE\t{cookie.get('path', '/')}\t")
                    f.write(f"{'TRUE' if cookie.get('secure', False) else 'FALSE'}\t")
            total_videos = 0
            for i, course_info in enumerate(processed_courses, 1):
                course = course_info['course']
                videos = [v for v in course_info['videos'] if v.get('type') == 'video']
                audios = [v for v in course_info['videos'] if v.get('type') == 'audio']
                
                print(f"\n{i}. {course['name']}")
                print(f"   Videos: {len(videos)}")
                print(f"   Audios: {len(audios)}")
                print(f"   Total: {len(course_info['videos'])}")
                total_videos += len(course_info['videos'])
            
            print(f"\n📹 Total media found: {total_videos}")
            total_videos = 0
            for i, course_info in enumerate(processed_courses, 1):
                course = course_info['course']
                print(f"\n{i}. {course['name']}")
            # 8. Save all unique URLs in a consolidated file
            print("\n💾 Saving consolidated URLs...")
            
            # Create set to eliminate global duplicates
            unique_urls = {}
            
            for course_info in processed_courses:
                course = course_info['course']
                for media in course_info['videos']:
                    media_id = media.get('video_id', media['url'])
                    if media_id not in unique_urls:
                        unique_urls[media_id] = {
                            'url': media['url'],
                            'type': media.get('type', 'unknown'),
                            'course': course['name']
                        }
            
            # Save unique URLs grouped by course and type
            with open('../output/logs/all_m3u8_urls.txt', 'w') as f:
                # Group by course
                courses_dict = {}
                for media_id, info in unique_urls.items():
                    course_name = info['course']
                    if course_name not in courses_dict:
                        courses_dict[course_name] = {'videos': [], 'audios': []}
                    
                    if info['type'] == 'video':
                        courses_dict[course_name]['videos'].append(info['url'])
                    elif info['type'] == 'audio':
                        courses_dict[course_name]['audios'].append(info['url'])
                
                # Write grouped by course and type
                for course_name, media in courses_dict.items():
                    total = len(media['videos']) + len(media['audios'])
                    f.write(f"# {course_name} ({len(media['videos'])} videos, {len(media['audios'])} audios)\n")
                    
                    if media['videos']:
                        f.write("## Videos\n")
                        for url in media['videos']:
                            f.write(f"{url}\n")
                    
                    if media['audios']:
                        f.write("## Audios\n")
                        for url in media['audios']:
                            f.write(f"{url}\n")
                    
                    f.write("\n")
            
            total_unique = len(unique_urls)
            videos_count = sum(1 for v in unique_urls.values() if v['type'] == 'video')
            audios_count = sum(1 for v in unique_urls.values() if v['type'] == 'audio')
            
            print(f"   ✅ {total_unique} unique media saved:")
            print(f"      • {videos_count} videos")
            print(f"      • {audios_count} audios")
            
            # 9. Final instructions
            print("\n" + "=" * 70)
            print("✅ PROCESS COMPLETED")
            print("=" * 70)
            print("\nGenerated files:")
            print(f"  - Screenshots: output/screenshots/ ({len(processed_courses) * 3}+ files)")
            print(f"  - HTML: output/html/ ({len(processed_courses)}+ files)")
            print(f"  - Logs: output/logs/")
            print(f"    • all_m3u8_urls.txt - All video URLs")
            print(f"    • cookies.txt - Cookies for yt-dlp")
            
            print("\n💡 To download the videos:")
            print("   cd scripts && python3 download_videos_auto.py")
            print("\n   Or manually with yt-dlp:")
            print("   yt-dlp -a ../output/logs/all_m3u8_urls.txt --cookies ../output/logs/cookies.txt -o '../output/videos/%(title)s.mp4'")
            
        finally:
            print("\n🔒 Closing browser...")
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Download videos from marczellklein.com courses',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Download all courses
  python3 download_course_videos_selenium.py
  
  # Download only course #1 (APEX)
  python3 download_course_videos_selenium.py -c 1
  
  # Download courses #1 and #3
  python3 download_course_videos_selenium.py -c 1 3
  
  # Download course #2 in headless mode (no window)
  python3 download_course_videos_selenium.py -c 2 --headless
        ''')
    
    parser.add_argument(
        '-c', '--courses',
        type=int,
        nargs='+',
        metavar='N',
        help='Course number(s) to process (1=APEX, 2=Hypnosis, 3=Simple). Without this argument all courses are processed.'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run browser without graphical interface'
    )
    
    args = parser.parse_args()
    
    # Validate course numbers
    if args.courses:
        invalid = [c for c in args.courses if c < 1 or c > 3]
        if invalid:
            parser.error(f"Invalid course numbers: {invalid}. Use 1, 2 or 3.")
        print(f"\n📋 Processing only course(s): {', '.join(map(str, args.courses))}")
    else:
        print("\n📋 Processing all courses")
    
    downloader = SeleniumCourseDownloader(
        headless=args.headless,
        course_filter=args.courses
    )
    downloader.run()

