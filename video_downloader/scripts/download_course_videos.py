#!/usr/bin/env python3
"""
Script to download videos from marczellklein.com course site
Test version - downloads a sample video
"""

import requests
from bs4 import BeautifulSoup
import re
import os
from urllib.parse import urljoin, urlparse
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / '.env')

# Credentials from environment
EMAIL = os.getenv('VIDEO_DOWNLOADER_EMAIL')
PASSWORD = os.getenv('VIDEO_DOWNLOADER_PASSWORD')

if not EMAIL or not PASSWORD:
    raise ValueError("VIDEO_DOWNLOADER_EMAIL and VIDEO_DOWNLOADER_PASSWORD must be set in .env file")

# URLs
BASE_URL = "https://members.marczellklein.com"
LOGIN_URL = "https://members.marczellklein.com/sign_in"  # Probando diferentes endpoints
COURSE_URL = "https://members.marczellklein.com/courses/library-v2"
OUTPUT_DIR = "downloaded_videos"

class CourseDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
    def login(self):
        """Authenticate on the site"""
        print("🔐 Starting login...")
        
        # First try to access the base site to see the structure
        print("   Exploring site structure...")
        base_response = self.session.get(BASE_URL)
        print(f"   Base URL status: {base_response.status_code}")
        
        # Save for analysis
        with open('base_page.html', 'w', encoding='utf-8') as f:
            f.write(base_response.text)
        
        # Search for login form in different common URLs
        login_endpoints = [
            "/sign_in",
            "/login",
            "/users/sign_in",
            "/account/login",
            "/auth/login"
        ]
        
        login_page = None
        for endpoint in login_endpoints:
            url = BASE_URL + endpoint
            print(f"   Testing: {url}")
            try:
                response = self.session.get(url)
                if response.status_code == 200 and ('email' in response.text.lower() or 'password' in response.text.lower()):
                    print(f"   ✓ Login form found at: {endpoint}")
                    login_page = response
                    LOGIN_URL = url
                    break
            except Exception as e:
                print(f"   × {endpoint}: {e}")
        
        if not login_page:
            print("   ⚠️  Standard login page not found")
            print("   Trying direct course access...")
            response = self.session.get(COURSE_URL)
            
            # Save the response
            with open('course_access_attempt.html', 'w', encoding='utf-8') as f:
                f.write(response.text)
            
            # If redirected to login, use that URL
            if 'sign' in response.url.lower() or 'login' in response.url.lower():
                print(f"   Redirected to: {response.url}")
                login_page = response
                LOGIN_URL = response.url
            else:
                # Maybe already authenticated or doesn't require login?
                if response.status_code == 200:
                    print("   ✓ Course access without explicit authentication")
                    return True
        
        if not login_page:
            print("   ❌ Could not determine authentication method")
            return False
        
        soup = BeautifulSoup(login_page.text, 'html.parser')
        
        # Search for the form
        form = soup.find('form')
        if not form:
            print("   ❌ Login form not found")
            return False
        
        # Extract form action URL
        form_action = form.get('action', LOGIN_URL)
        if not form_action.startswith('http'):
            form_action = urljoin(BASE_URL, form_action)
        
        print(f"   Form action: {form_action}")
        
        # Search for all form fields
        login_data = {}
        
        # Add all hidden fields
        for hidden in form.find_all('input', {'type': 'hidden'}):
            name = hidden.get('name')
            value = hidden.get('value', '')
            if name:
                login_data[name] = value
                print(f"   Hidden field: {name}")
        
        # Search for email/username fields
        email_field = form.find('input', {'type': 'email'}) or \
                     form.find('input', {'name': re.compile(r'email|user', re.I)})
        if email_field:
            email_name = email_field.get('name', 'email')
            login_data[email_name] = EMAIL
            print(f"   Email field: {email_name}")
        
        # Search for password field
        password_field = form.find('input', {'type': 'password'})
        if password_field:
            password_name = password_field.get('name', 'password')
            login_data[password_name] = PASSWORD
            print(f"   Password field: {password_name}")
        
        if not email_field or not password_field:
            print("   ⚠️  Standard email/password fields not found")
            # Try with common names
            login_data.update({
                'email': EMAIL,
                'password': PASSWORD,
                'user[email]': EMAIL,
                'user[password]': PASSWORD
            })
        
        print(f"   Sending credentials to: {form_action}")
        
        # Attempt login
        response = self.session.post(form_action, data=login_data, allow_redirects=True)
        
        print(f"   Response status: {response.status_code}")
        print(f"   Final URL: {response.url}")
        
        # Save response
        with open('login_response.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        # Check if login was successful
        # Verification methods:
        # 1. Search for "logout" or "sign out" on page
        if re.search(r'logout|sign.?out', response.text, re.I):
            print("✅ Login successful (logout found)")
            return True
        
        # 2. No error message
        if not re.search(r'invalid|incorrect|wrong|error', response.text, re.I):
            # 3. Try to access course
            test_response = self.session.get(COURSE_URL)
            if test_response.status_code == 200:
                # Check that we weren't redirected to login
                if 'sign' not in test_response.url.lower() and 'login' not in test_response.url.lower():
                    print("✅ Login successful (course access verified)")
                    return True
        
        print("❌ Login failed - check generated HTML files")
        return False
    
    def get_apex_videos(self):
        """Get the list of videos from Apex section"""
        print("\n📚 Accessing Apex section...")
        
        response = self.session.get(COURSE_URL)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Save HTML for analysis
        with open('page_structure.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print("   HTML saved to 'page_structure.html' for analysis")
        
        # Search for Apex section
        apex_section = None
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'div']):
            if 'apex' in heading.get_text().lower():
                apex_section = heading
                print(f"   Apex section found: {heading.get_text().strip()}")
                break
        
        if not apex_section:
            print("   ⚠️  Apex section not found directly")
            print("   Searching for videos throughout the page...")
        
        # Search for all video links
        video_links = []
        
        # Search for different common patterns
        patterns = [
            soup.find_all('a', href=re.compile(r'lesson|video|watch|lecture', re.I)),
            soup.find_all('a', {'class': re.compile(r'lesson|video|lecture', re.I)}),
            soup.find_all('video'),
            soup.find_all('iframe'),
        ]
        
        for pattern_results in patterns:
            for element in pattern_results:
                if element.name == 'a':
                    href = element.get('href')
                    text = element.get_text().strip()
                    if href:
                        full_url = urljoin(COURSE_URL, href)
                        video_links.append({
                            'url': full_url,
                            'title': text or 'No title',
                            'type': 'link'
                        })
                elif element.name in ['video', 'iframe']:
                    src = element.get('src')
                    if src:
                        video_links.append({
                            'url': src,
                            'title': 'Direct video',
                            'type': element.name
                        })
        
        # Remove duplicates
        seen = set()
        unique_videos = []
        for vid in video_links:
            if vid['url'] not in seen:
                seen.add(vid['url'])
                unique_videos.append(vid)
        
        print(f"\n   📹 {len(unique_videos)} video links found")
        for i, vid in enumerate(unique_videos[:10], 1):  # Show only first 10
            print(f"   {i}. {vid['title'][:60]} - {vid['url'][:80]}")
        
        return unique_videos
    
    def analyze_video_page(self, video_url):
        """Analyze a video page to find the download URL"""
        print(f"\n🔍 Analyzing video page: {video_url}")
        
        response = self.session.get(video_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Search for video player
        video_sources = []
        
        # 1. Search for <video> tags
        for video_tag in soup.find_all('video'):
            # Search for <source> inside video
            for source in video_tag.find_all('source'):
                src = source.get('src')
                if src:
                    video_sources.append({
                        'url': urljoin(video_url, src),
                        'type': 'video_tag',
                        'quality': source.get('label', 'unknown')
                    })
            # Also direct src of video
            if video_tag.get('src'):
                video_sources.append({
                    'url': urljoin(video_url, video_tag['src']),
                    'type': 'video_tag',
                    'quality': 'default'
                })
        
        # 2. Search for iframes (Vimeo, YouTube, Wistia, etc.)
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src')
            if src:
                video_sources.append({
                    'url': src,
                    'type': 'iframe',
                    'quality': 'embedded'
                })
        
        # 3. Search in JavaScript for video URLs
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Search for video URLs in JS
                video_urls = re.findall(r'https?://[^\s<>"\']+\.(?:mp4|m3u8|webm)', script.string)
                for url in video_urls:
                    video_sources.append({
                        'url': url,
                        'type': 'javascript',
                        'quality': 'from_js'
                    })
                
                # Search for Vimeo/Wistia configurations
                vimeo_match = re.search(r'vimeo\.com/video/(\d+)', script.string)
                if vimeo_match:
                    video_sources.append({
                        'url': f"https://player.vimeo.com/video/{vimeo_match.group(1)}",
                        'type': 'vimeo',
                        'quality': 'vimeo'
                    })
                
                wistia_match = re.search(r'wistia\.com/medias/(\w+)', script.string)
                if wistia_match:
                    video_sources.append({
                        'url': f"https://fast.wistia.net/embed/medias/{wistia_match.group(1)}",
                        'type': 'wistia',
                        'quality': 'wistia'
                    })
        
        print(f"   📹 {len(video_sources)} video sources found:")
        for i, source in enumerate(video_sources, 1):
            print(f"   {i}. [{source['type']}] {source['url'][:100]}")
        
        # Save video page HTML
        with open('video_page.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print("   HTML saved to 'video_page.html' for analysis")
        
        return video_sources
    
    def download_video(self, video_url, filename):
        """Download a video"""
        print(f"\n⬇️  Downloading video: {filename}")
        
        # Create output directory
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        try:
            response = self.session.get(video_url, stream=True)
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
                            print(f"\r   Progress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='')
                    print()
                else:
                    f.write(response.content)
            
            print(f"✅ Video downloaded: {filepath}")
            return True
            
        except Exception as e:
            print(f"❌ Download error: {e}")
            return False
    
    def run(self):
        """Execute the complete process"""
        print("=" * 70)
        print("🎬 VIDEO DOWNLOADER - MARC ZELL KLEIN")
        print("=" * 70)
        
        # 1. Login
        if not self.login():
            print("\n❌ Could not login. Check credentials.")
            return
        
        # 2. Get Apex videos
        videos = self.get_apex_videos()
        
        if not videos:
            print("\n⚠️  No videos found. Check site structure.")
            return
        
        # 3. Analyze first video as test
        print("\n" + "=" * 70)
        print("📹 ANALYZING FIRST VIDEO AS TEST")
        print("=" * 70)
        
        first_video = videos[0]
        print(f"\nSelected video: {first_video['title']}")
        print(f"URL: {first_video['url']}")
        
        # Only analyze if it's a link (not a direct video)
        if first_video['type'] == 'link':
            sources = self.analyze_video_page(first_video['url'])
            
            if sources:
                # Try to download first available source
                for source in sources:
                    if source['type'] in ['video_tag', 'javascript'] and source['url'].endswith('.mp4'):
                        filename = f"test_video_{int(time.time())}.mp4"
                        if self.download_video(source['url'], filename):
                            break
                    else:
                        print(f"\n   ℹ️  Source type '{source['type']}' requires special processing")
                        if source['type'] in ['vimeo', 'wistia']:
                            print(f"   You'll need additional tools to download from {source['type']}")
        else:
            # It's a direct video, try to download
            if first_video['url'].endswith('.mp4'):
                filename = f"test_video_{int(time.time())}.mp4"
                self.download_video(first_video['url'], filename)
            else:
                print(f"\n   ℹ️  Video is not a direct MP4: {first_video['url']}")
        
        print("\n" + "=" * 70)
        print("✅ ANALYSIS COMPLETED")
        print("=" * 70)
        print("\nCheck generated files:")
        print("  - page_structure.html: Main page structure")
        print("  - video_page.html: Video page structure")
        print(f"  - {OUTPUT_DIR}/: Downloaded videos")

if __name__ == "__main__":
    downloader = CourseDownloader()
    downloader.run()
