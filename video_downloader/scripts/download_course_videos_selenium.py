#!/usr/bin/env python3
"""
Script to download videos from marczellklein.com course site
Version with Selenium to handle dynamic JavaScript content
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

# URLs
BASE_URL = "https://members.marczellklein.com"
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
        self.setup_driver()
        
    def setup_driver(self):
        """Configure Chrome driver"""
        print("🔧 Setting up Chrome browser...")
        
        options = webdriver.ChromeOptions()
        
        if self.headless:
            options.add_argument('--headless')
        
        # Options for better performance and compatibility
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Enable network logs to capture requests
        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        
        # User agent
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            
            # Activate Chrome DevTools Protocol to capture network requests
            self.driver.execute_cdp_cmd('Network.enable', {})
            
            print("✅ Chrome browser started")
        except Exception as e:
            print(f"❌ Error starting Chrome: {e}")
            print("\nMake sure you have ChromeDriver installed:")
            print("  brew install chromedriver")
            raise
    
    def login(self):
        """Authenticate on the site"""
        print("\n🔐 Starting login...")
        
        try:
            # Go to main page
            print(f"   Navigating to: {BASE_URL}")
            self.driver.get(BASE_URL)
            time.sleep(3)  # Wait for JavaScript to load
            
            # Save screenshot
            self.driver.save_screenshot('../output/screenshots/step1_homepage.png')
            print("   Screenshot saved: step1_homepage.png")
            
            # Search for login/sign in button
            login_selectors = [
                "//button[contains(text(), 'Sign In')]",
                "//button[contains(text(), 'Log In')]",
                "//a[contains(text(), 'Sign In')]",
                "//a[contains(text(), 'Log In')]",
                "//button[contains(@class, 'login')]",
                "//a[contains(@class, 'login')]",
                "//input[@type='email']",  # If form is already visible
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    if elements:
                        login_button = elements[0]
                        print(f"   ✓ Login element found: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                print("   ⚠️  Login button not found")
                print("   Saving current page...")
                with open('../output/html/page_source_base.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                
                # Try direct access to course page
                print(f"   Attempting direct access to: {COURSE_URL}")
                self.driver.get(COURSE_URL)
                time.sleep(5)
                
                self.driver.save_screenshot('../output/screenshots/step2_course_direct.png')
                
                # Check if there's a login form now
                login_button = self._find_login_elements()
            
            # If we found a button, click it
            if login_button and login_button.tag_name in ['button', 'a']:
                print("   Clicking login button...")
                login_button.click()
                time.sleep(3)
                self.driver.save_screenshot('../output/screenshots/step3_after_click.png')
            
            # Now search for email and password fields
            print("   Looking for form fields...")
            email_field = self._find_email_field()
            password_field = self._find_password_field()
            
            if not email_field or not password_field:
                print("   ❌ Email/password fields not found")
                with open('../output/html/page_source_login.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                return False
            
            # Fill form
            print("   Entering credentials...")
            email_field.clear()
            email_field.send_keys(EMAIL)
            time.sleep(0.5)
            
            password_field.clear()
            password_field.send_keys(PASSWORD)
            time.sleep(0.5)
            
            self.driver.save_screenshot('../output/screenshots/step4_filled_form.png')
            
            # Find and click submit button
            submit_button = self._find_submit_button()
            if submit_button:
                print("   Submitting form...")
                submit_button.click()
            else:
                print("   Submitting form with Enter...")
                password_field.send_keys('\n')
            
            # Wait for page to load after login
            print("   Waiting for server response...")
            time.sleep(8)  # More time to load
            self.driver.save_screenshot('../output/screenshots/step5_after_login.png')
            
            # Check if login was successful
            current_url = self.driver.current_url
            page_source = self.driver.page_source.lower()
            
            print(f"   Current URL: {current_url}")
            
            # Save page after login
            with open('../output/html/page_after_login.html', 'w', encoding='utf-8') as f:
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
            
            # Check if we're on a different page than login
            if 'login' not in current_url.lower() and 'sign' not in current_url.lower():
                print("✅ Login successful (redirected away from login)")
                return True
            
            # Check for explicit error messages
            error_indicators = ['invalid', 'incorrect', 'wrong', 'failed', 'denied']
            error_found = False
            for error in error_indicators:
                if error in page_source:
                    error_found = True
                    break
            
            if error_found:
                print("❌ Login failed - error message detected")
                with open('../output/html/page_source_error.html', 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                return False
            
            # If no explicit error, assume it worked
            print("✅ Login completed (no errors detected)")
            return True
            
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
    
    def find_videos(self, course_index=0):
        """Find all videos on current course page"""
        print("\n🔍 Navigating through course playlist...")
        
        all_videos_urls = []
        
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
        
        while category_count < max_categories:
            category_count += 1
            print(f"\n📚 Processing CATEGORY #{category_count}...")
            
            # Wait for page to stabilize
            time.sleep(3)
            
            try:
                # 1. Read how many lessons are in this category
                try:
                    lesson_counter = self.driver.find_element(By.XPATH, '//*[@id="playlist-wrapper"]/div[1]/div/div/p')
                    counter_text = lesson_counter.text  # Format: "Lesson 1 of 8" or "112 Lessons"
                    print(f"   📊 {counter_text}")
                    
                    # Extract total lesson number
                    import re
                    # Try different formats
                    match = re.search(r'of (\d+)', counter_text)  # "Lesson 1 of 8"
                    if not match:
                        match = re.search(r'(\d+)\s+Lesson', counter_text)  # "112 Lessons"
                    
                    if match:
                        total_lessons_in_category = int(match.group(1))
                    else:
                        total_lessons_in_category = 200  # Higher default to avoid missing lessons
                except:
                    total_lessons_in_category = 200  # Higher default if not found
                    print(f"   ⚠️  Could not read counter, assuming {total_lessons_in_category} lessons")
                
                # 2. Search for playlist container
                playlist_container = self.driver.find_element(By.XPATH, playlist_container_xpath)
                print("   ✓ Container found")
                
                # 3. Search for ALL lesson items (with UUID IDs)
                playlist_items = playlist_container.find_elements(
                    By.XPATH, 
                    './/*[@id and string-length(@id) > 30]'
                )
                
                print(f"   ✓ {len(playlist_items)} item(s) found in playlist")
                
                # 4. Track URLs already seen in this category
                seen_urls_in_category = set()
                
                # 4.5 NEW: Click on load-next-post MULTIPLE TIMES to load ALL content
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
                
                # 5. Iterate over each lesson in the playlist
                lessons_processed = 0
                lessons_with_content = 0
                
                for idx, item in enumerate(playlist_items, 1):
                    # Limit to the number of lessons in the category
                    if lessons_processed >= total_lessons_in_category:
                        break
                    
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
                        
                        print(f"      🎯 Lesson #{lessons_processed + 1} (ID: {item_id[:36]})")
                        
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
                        
                        # Capture URLs from performance logs after playback
                        # DO NOT use self.get_network_logs() because it filters globally
                        # Capture directly without global filtering
                        lesson_urls = []
                        try:
                            logs = self.driver.get_log('performance')
                            for entry in logs:
                                try:
                                    log = json.loads(entry['message'])['message']
                                    if log['method'] == 'Network.responseReceived':
                                        url = log['params']['response']['url']
                                        # Only master.m3u8 with token
                                        if 'master.m3u8' in url and 'token=' in url:
                                            video_id = url.split('/videos/')[-1].split('_')[0] if '/videos/' in url else url.split('/')[-1][:36]
                                            # Filter only by URLs seen IN THIS CATEGORY
                                            if url not in seen_urls_in_category:
                                                lesson_urls.append({
                                                    'url': url,
                                                    'type': 'video',
                                                    'video_id': video_id
                                                })
                                                seen_urls_in_category.add(url)
                                                self.captured_video_ids.add(video_id)
                                except:
                                    continue
                        except:
                            pass
                        
                        if lesson_urls:
                            videos = [u for u in lesson_urls if u['type'] == 'video']
                            audios = [u for u in lesson_urls if u['type'] == 'audio']
                            
                            if videos or audios:
                                print(f"         ✅ {len(videos)} video(s) + {len(audios)} audio(s)")
                                all_videos_urls.extend(lesson_urls)
                                lessons_with_content += 1
                                
                                # 🚀 WRITE IMMEDIATELY to file for async download
                                output_file = os.path.join(LOGS_DIR, 'all_m3u8_urls.txt')
                                with open(output_file, 'a', encoding='utf-8') as f:
                                    for item in lesson_urls:
                                        f.write(f"{item['url']}\n")
                                        f.flush()  # Forzar escritura inmediata
                                print(f"         💾 URLs written → download started")
                        
                    except Exception as e:
                        if 'stale element' not in str(e).lower():
                            print(f"         ⚠️  Error: {str(e)[:50]}")
                        continue
                
                if lessons_with_content > 0:
                    print(f"   ✅ Lessons with content: {lessons_with_content}/{lessons_processed}")
                else:
                    # If no content by clicking, capture visible DOM
                    print(f"   📹 Capturing visible DOM content...")
                    time.sleep(4)
                    lesson_urls = self.extract_video_from_dom()
                    
                    if lesson_urls:
                        for url in lesson_urls:
                            url_type = 'audio' if any(ext in url for ext in ['.mp3', '.m4a', '.aac']) else 'video'
                            url_item = {
                                'url': url,
                                'type': url_type,
                                'video_id': self.extract_video_id(url)
                            }
                            all_videos_urls.append(url_item)
                            
                            # 🚀 WRITE IMMEDIATELY to file for async download
                            output_file = os.path.join(LOGS_DIR, 'all_m3u8_urls.txt')
                            with open(output_file, 'a', encoding='utf-8') as f:
                                f.write(f"{url}\n")
                                f.flush()  # Force immediate write
                        
                        videos = [u for u in all_videos_urls if u['type'] == 'video']
                        audios = [u for u in all_videos_urls if u['type'] == 'audio']
                        print(f"   💾 {len(lesson_urls)} URLs written → download started")
                        if videos:
                            print(f"   ✓ {len(videos)} video(s) captured")
                        if audios:
                            print(f"   ✓ {len(audios)} audio(s) captured")
                    else:
                        print(f"   ⚠️  No URLs captured in this category")
                
                # 5. Save screenshot of current category
                self.driver.save_screenshot(f'../output/screenshots/course_{course_index}_category_{category_count}.png')
                
                # 6. Click on "Next Category" to advance to the next one
                # 6. Click on "Next Category" to advance to the next one
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
        
        return all_videos_urls
    
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
        """Execute the complete process for multiple courses"""
        print("=" * 70)
        print("🎬 VIDEO DOWNLOADER - MARC ZELL KLEIN (SELENIUM)")
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
            
            print(f"   📋 Will process {len(courses)} course(s)\n")
            
            # 3. Process each course
            for course in courses:
                print("\n" + "=" * 70)
                print(f"📚 PROCESSING COURSE #{course['index']} of {len(courses)}")
                print("=" * 70)
                
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
                
                # 4. Navigate through all course lessons and capture videos
                print(f"\n🎬 Navigating through lessons of '{course['name']}'...")
                videos = self.find_videos(course_index=course['index'])
                
                # Save course information
                course_info = {
                    'course': course,
                    'videos_found': len(videos),
                    'videos': videos
                }
                processed_courses.append(course_info)
                
                print(f"\n✅ Course '{course['name']}' completed: {len(videos)} videos found")
                
                # 5. Return to course page to process the next one
                if course['index'] < len(courses):
                    print(f"\n🔄 Returning to course list to process next...")
                    self.driver.get(COURSE_URL)
                    time.sleep(4)  # Wait for course list to load
                    
                    # Verify we're on the correct page
                    if 'library-v2' in self.driver.current_url:
                        print("   ✓ Back in course list")
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

