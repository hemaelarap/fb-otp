"""
Facebook OTP Browser Automation
================================
Uses Selenium to automate Facebook account recovery and OTP request
Opens real browser, fills forms, clicks buttons

Designed by: Doctor Kayf (@Doc_kayf)
             https://t.me/Doc_kayf

Features:
- Real browser automation (bypasses anti-bot)
- Headless mode option
- Batch processing support
- Detailed logging

Requirements:
    pip install selenium webdriver-manager

Usage:
    python fb_otp_browser.py +201234567890
    python fb_otp_browser.py numbers.txt
"""

import sys
import io
import os
import requests
import time
import re
import random
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fix console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("[ERROR] Selenium not installed! Run: pip install selenium webdriver-manager")
    sys.exit(1)

# Try to import seleniumwire for authenticated proxy support
try:
    from seleniumwire import webdriver as wire_webdriver
    SELENIUMWIRE_AVAILABLE = True
except ImportError:
    SELENIUMWIRE_AVAILABLE = False
    SELENIUMWIRE_AVAILABLE = True
except ImportError:
    SELENIUMWIRE_AVAILABLE = False
    # Only warn if proxy is actually used later, or just suppress noisy warning
    pass

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("[WARNING] webdriver-manager not installed. Run: pip install webdriver-manager")
    ChromeDriverManager = None

try:
    import undetected_chromedriver as uc
    UNDETECTED_AVAILABLE = True
except ImportError:
    print("[WARNING] undetected-chromedriver not installed. Run: pip install undetected-chromedriver")
    UNDETECTED_AVAILABLE = False

# Colors
class C:
    B = '\033[94m'
    G = '\033[92m'
    Y = '\033[93m'
    R = '\033[91m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

# Shared Statistics Class for Parallel Processing
class Stats:
    """Thread-safe statistics tracker"""
    def __init__(self, total):
        self.lock = threading.Lock()
        self.total = total
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.not_found = 0
    
    def update(self, status):
        with self.lock:
            self.processed += 1
            if status == "OTP_SENT":
                self.success += 1
            elif status == "NOT_FOUND":
                self.not_found += 1
            else:
                self.failed += 1
    
    def display(self):
        """Display current statistics"""
        with self.lock:
            pct = (self.processed / self.total * 100) if self.total > 0 else 0
            print(f"\n{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════╗{C.END}")
            print(f"{C.BOLD}{C.CYAN}║{C.END}              📊 LIVE STATISTICS                          {C.BOLD}{C.CYAN}║{C.END}")
            print(f"{C.BOLD}{C.CYAN}╠══════════════════════════════════════════════════════════╣{C.END}")
            print(f"{C.BOLD}{C.CYAN}║{C.END}  📱 Total Numbers:     {self.total:<10}                     {C.BOLD}{C.CYAN}║{C.END}")
            print(f"{C.BOLD}{C.CYAN}║{C.END}  ⚡ Processed:         {self.processed:<10} ({pct:.1f}%)             {C.BOLD}{C.CYAN}║{C.END}")
            print(f"{C.BOLD}{C.CYAN}║{C.END}  {C.G}✓ Success (OTP Sent):{C.END} {self.success:<10}                     {C.BOLD}{C.CYAN}║{C.END}")
            print(f"{C.BOLD}{C.CYAN}║{C.END}  {C.Y}⚠ Not Found:{C.END}         {self.not_found:<10}                     {C.BOLD}{C.CYAN}║{C.END}")
            print(f"{C.BOLD}{C.CYAN}║{C.END}  {C.R}✗ Failed/Errors:{C.END}     {self.failed:<10}                     {C.BOLD}{C.CYAN}║{C.END}")
            print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════════╝{C.END}\n")

def log(msg, level="INFO"):
    t = datetime.now().strftime("%H:%M:%S")
    colors = {"INFO": C.B, "OK": C.G, "WARN": C.Y, "ERROR": C.R, "SUCCESS": C.G + C.BOLD}
    c = colors.get(level, "")
    print(f"{C.CYAN}[{t}]{C.END} {c}[{level}] {msg}{C.END}")


class ProxyManager:
    """Manages proxy rotation from a file"""
    
    def __init__(self, proxy_file=None):
        self.proxies = []
        self.current_index = 0
        self.lock = threading.Lock()
        
        if proxy_file:
            self.load_proxies(proxy_file)
    
    def load_proxies(self, filename):
        """Load proxies from file. Format: host:port:username:password"""
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.proxies.append(line)
            log(f"Loaded {len(self.proxies)} proxies from {filename}", "OK")
        except FileNotFoundError:
            log(f"Proxy file not found: {filename}", "WARN")
        except Exception as e:
            log(f"Error loading proxies: {e}", "ERROR")
    
    def get_next(self):
        """Get next proxy in rotation (thread-safe)"""
        if not self.proxies:
            return None
        with self.lock:
            proxy = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            return proxy
    
    def get_random(self):
        """Get a random proxy"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def parse_proxy(self, proxy_string):
        """Parse proxy string to components
        Format: host:port:username:password
        Returns dict with host, port, username, password
        """
        if not proxy_string:
            return None
        
        parts = proxy_string.split(':')
        if len(parts) >= 4:
            return {
                'host': parts[0],
                'port': parts[1],
                'username': parts[2],
                'password': ':'.join(parts[3:])  # Handle passwords with colons
            }
        elif len(parts) == 2:
            return {
                'host': parts[0],
                'port': parts[1],
                'username': None,
                'password': None
            }
        return None


class FacebookOTPBrowser:
    """Facebook OTP Automation using Selenium Browser"""
    
    def __init__(self, headless=False, proxy=None, proxy_manager=None):
        self.driver = None
        self.headless = headless
        self.wait_time = 15 # Increased default wait
        self.proxy = proxy
        self.proxy_manager = proxy_manager
        
    
    def _save_failure_snapshot(self, step_name):
        """Analyze failure context: Save screenshot, Log URL & Titles"""
        try:
            timestamp = int(time.time())
            # 1. Log Critical Info
            url = self.driver.current_url
            title = self.driver.title
            log(f"FAILURE TRACE [{step_name}] | URL: {url} | Title: {title}", "ERROR")
            
            # 2. Check for common error texts "Account Suspended", "No Search Results"
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            if "suspended" in page_text:
                log("!! DIAGNOSIS: Account appears suspended/disabled !!", "ERROR")
            elif "no result" in page_text or "didn't match" in page_text:
                log("!! DIAGNOSIS: Search returned no results !!", "WARN")
            elif "try again" in page_text:
                log("!! DIAGNOSIS: Facebook asking to try again (Rate Limit?) !!", "WARN")
            
            # 3. Save Screenshot (if on server, this might not be viewable easily, but good for local)
            filename = f"fail_{step_name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            log(f"Screenshot saved to: {filename}", "INFO")
            
        except Exception as e:
            log(f"Failed to save failure snapshot: {e}", "WARN")

    def _setup_driver(self):
        """Setup Chrome WebDriver with optional proxy support"""
        log("Setting up Chrome browser...")
        
        options = Options()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # Anti-detection options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-gpu")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=ar")  # Force Arabic language preference
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        
        # Realistic User Agent (Updated to Chrome 133)
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
        
        # Disable automation flags (Crucial for Headless)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Configure proxy if available
        proxy_string = self.proxy
        if not proxy_string and self.proxy_manager:
            proxy_string = self.proxy_manager.get_next()
        
        if proxy_string:
            proxy_data = None
            if self.proxy_manager:
                proxy_data = self.proxy_manager.parse_proxy(proxy_string)
            else:
                parts = proxy_string.split(':')
                if len(parts) >= 4:
                    proxy_data = {
                        'host': parts[0],
                        'port': parts[1],
                        'username': parts[2],
                        'password': ':'.join(parts[3:])
                    }
                elif len(parts) == 2:
                    proxy_data = {
                        'host': parts[0],
                        'port': parts[1],
                        'username': None,
                        'password': None
                    }
            
            if proxy_data:
                proxy_host = proxy_data['host']
                proxy_port = proxy_data['port']
                proxy_user = proxy_data.get('username')
                proxy_pass = proxy_data.get('password')
                
                if proxy_user and proxy_pass:
                    # Use folder-based extension with --load-extension
                    import os
                    
                    # Get the extension folder path (relative to script)
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    extension_dir = os.path.join(script_dir, 'proxy_extension')
                    
                    # Create extension directory if not exists
                    os.makedirs(extension_dir, exist_ok=True)
                    
                    # Write manifest.json
                    manifest_json = '''{
    "version": "1.0.0",
    "manifest_version": 2,
    "name": "Proxy Auth Extension",
    "permissions": [
        "proxy",
        "tabs",
        "unlimitedStorage",
        "storage",
        "<all_urls>",
        "webRequest",
        "webRequestBlocking"
    ],
    "background": {
        "scripts": ["background.js"],
        "persistent": true
    },
    "minimum_chrome_version": "22.0.0"
}'''
                    with open(os.path.join(extension_dir, 'manifest.json'), 'w') as f:
                        f.write(manifest_json)
                    
                    # Write background.js with proxy credentials
                    # Use https scheme for Oxylabs proxies
                    proxy_scheme = "https" if "oxylabs" in proxy_host.lower() else "http"
                    background_js = f'''var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{
            scheme: "{proxy_scheme}",
            host: "{proxy_host}",
            port: {proxy_port}
        }},
        bypassList: ["localhost"]
    }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{
    console.log("Proxy configured: {proxy_host}:{proxy_port}");
}});
function callbackFn(details) {{
    return {{
        authCredentials: {{
            username: "{proxy_user}",
            password: "{proxy_pass}"
        }}
    }};
}}
chrome.webRequest.onAuthRequired.addListener(
    callbackFn,
    {{urls: ["<all_urls>"]}},
    ['blocking']
);
console.log("Proxy Auth Extension Active");'''
                    
                    with open(os.path.join(extension_dir, 'background.js'), 'w') as f:
                        f.write(background_js)
                    
                    # Load extension using --load-extension flag
                    options.add_argument(f"--load-extension={extension_dir}")
                    log(f"Proxy extension loaded: {proxy_host}:{proxy_port}", "OK")
                else:
                    # Simple proxy without auth
                    options.add_argument(f"--proxy-server=http://{proxy_host}:{proxy_port}")
                    log(f"Using proxy: {proxy_host}:{proxy_port}", "INFO")
        
        try:
            # Use undetected_chromedriver if available (better stealth)
            if UNDETECTED_AVAILABLE:
                log("Using undetected-chromedriver for enhanced stealth", "INFO")
                self.driver = uc.Chrome(
                    options=options,
                    headless=self.headless,
                    use_subprocess=False,
                    version_main=None  # Auto-detect Chrome version
                )
                log("Undetected Chrome browser ready!", "OK")
            elif ChromeDriverManager:
                try:
                    driver_path = ChromeDriverManager().install()
                    # FIX: webdriver-manager 4.0.1 sometimes returns THIRD_PARTY_NOTICES
                    if "THIRD_PARTY_NOTICES" in driver_path:
                        import os
                        base_dir = os.path.dirname(driver_path)
                        real_path = os.path.join(base_dir, "chromedriver")
                        if os.path.exists(real_path):
                            log(f"Correcting driver path from {driver_path} to {real_path}", "INFO")
                            driver_path = real_path
                            os.chmod(driver_path, 0o755) # Ensure executable
                            
                    service = Service(driver_path)
                    self.driver = webdriver.Chrome(service=service, options=options)
                except Exception as e:
                    # Fallback for some systems
                    log(f"DriverManager failed, trying default: {e}", "WARN")
                    self.driver = webdriver.Chrome(options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
            
            # Execute script to hide webdriver (only if not using undetected_chromedriver)
            if not UNDETECTED_AVAILABLE:
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            if not UNDETECTED_AVAILABLE:
                log("Chrome browser ready!", "OK")
            return True
            
        except Exception as e:
            log(f"Failed to setup Chrome: {e}", "ERROR")
            return False
    
    def _close_driver(self):
        """Close the browser"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def _wait_for_element(self, by, value, timeout=None):
        """Wait for element to be present"""
        timeout = timeout or self.wait_time
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            return None
    
    def _wait_and_click(self, by, value, timeout=None):
        """Wait for element and click"""
        timeout = timeout or self.wait_time
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((by, value))
            )
            element.click()
            return True
        except TimeoutException:
            return False
            
    def random_sleep(self, min_time, max_time):
        """Sleep for a random amount of time"""
        sleep_time = random.uniform(min_time, max_time)
        time.sleep(sleep_time)

    def send_telegram_photo(self, caption, file_path):
        """Send a photo to the configured Telegram chat."""
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            log("Telegram credentials not found, skipping photo send.", "WARN")
            return

        try:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            with open(file_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": chat_id, "caption": caption}
                response = requests.post(url, files=files, data=data)
                
            if response.status_code == 200:
                log(f"Sent Telegram photo: {caption}", "OK")
            else:
                log(f"Failed to send Telegram photo: {response.text}", "WARN")
        except Exception as e:
            log(f"Error sending Telegram photo: {e}", "WARN")

    def step1_open_recovery_page(self):
        """Step 1: Open Facebook, handle cookies, and navigate to recovery"""
        log("Step 1: Opening Facebook Recovery Page...")
        try:
            self.driver.get('https://www.facebook.com/login/identify')
            self.random_sleep(5, 8)  # Increased wait for cookie popup and page load (Slow down)
            
            # Handle Cookie Consent (European/International IPs)
            self._handle_cookie_consent()
            
            return True
        except Exception as e:
            log(f"Error opening page: {e}", "ERROR")
            self._save_failure_snapshot("step1_open_page")
            return False

    def _handle_cookie_consent(self):
        """Click 'Decline optional cookies' - Clean Version"""
        log("Checking for cookie consent...", "INFO")
        try:
            # Wait for the button to appear (timeout 5 seconds)
            wait = WebDriverWait(self.driver, 5)
            
            button = None
            try:
                # First try Arabic
                button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[aria-label="رفض ملفات تعريف الارتباط الاختيارية"]')))
                log("Found Arabic cookie button.", "INFO")
            except:
                try:
                    # Then try English
                    button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'div[aria-label="Decline optional cookies"]')))
                    log("Found English cookie button.", "INFO")
                except:
                    log("No cookie popup found.", "INFO")
                    return

            if button:
                time.sleep(3)  # Wait before clicking to simulate human behavior
                button.click()
                log("Clicked 'Decline optional cookies' successfully.", "SUCCESS")
                time.sleep(2)
            
        except Exception as e:
            log(f"Cookie handler error: {e}", "WARN")
    
    def step2_enter_phone(self, phone):
        """Step 2: Enter phone number in search field"""
        log(f"Step 2: Entering phone number: {phone}...")
        self._handle_cookie_consent()  # Ensure cookies don't block input
        
        try:
            # Find the email/phone input field - try multiple times
            input_selectors = [
                (By.ID, "identify_email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.XPATH, "//input[@placeholder]"),
                (By.CSS_SELECTOR, "input"),
            ]
            
            input_field = None
            for attempt in range(3):  # Try 3 times
                for by, selector in input_selectors:
                    try:
                        input_field = WebDriverWait(self.driver, 8).until(
                            EC.presence_of_element_located((by, selector))
                        )
                        if input_field and input_field.is_displayed():
                            break
                    except:
                        continue
                if input_field:
                    break
                time.sleep(1)
            
            if not input_field:
                log("Could not find input field", "ERROR")
                return False
            
            # Clear and enter phone
            input_field.clear()
            input_field.send_keys(phone)
            time.sleep(0.2)
            
            log("Phone number entered!", "OK")
            return True
            
        except Exception as e:
            log(f"Error entering phone: {e}", "ERROR")
            return False
    
    def step3_click_search(self):
        """Step 3: Click the search button"""
        log("Step 3: Clicking search button...")
        self._handle_cookie_consent() 
        
        try:
            # Try different button selectors
            button_selectors = [
                (By.NAME, "did_submit"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Search')]"),
                (By.XPATH, "//button[contains(text(), 'بحث')]"),
                (By.XPATH, "//input[@value='Search']"),
                (By.CSS_SELECTOR, "[data-testid='royal_email_next_button']"),
            ]
            
            for by, selector in button_selectors:
                try:
                    button = self.driver.find_element(by, selector)
                    if button:
                        button.click()
                        log("Search button clicked!", "OK")
                        time.sleep(1)
                        return True
                except:
                    continue
            
            # Try pressing Enter as fallback
            try:
                input_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='email']")
                input_field.send_keys(Keys.ENTER)
                log("Pressed Enter to search", "OK")
                time.sleep(1)
                return True
            except:
                pass
            
            log("Could not find search button", "WARN")
            return False
            
        except Exception as e:
            log(f"Error clicking search: {e}", "ERROR")
            return False
    
    def step4_check_account_found(self):
        """Step 4: Check if account was found"""
        log("Step 4: Checking if account exists...")
        self._handle_cookie_consent()
        
        # Wait for page to load properly
        time.sleep(2)
        
        try:
            page_source = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            # FIRST: Check URL for recovery (most reliable)
            if "recover" in current_url or "reset" in current_url:
                log("Account FOUND (URL check)!", "OK")
                return "FOUND"
            
            # SECOND: Check for recovery page indicators (check FOUND first!)
            found_indicators = [
                "recover",
                "reset",
                "your account",
                "send code",
                "reset your password",
                "حسابك",
                "إرسال الرمز",
                "إعادة تعيين",
            ]
            
            for indicator in found_indicators:
                if indicator in page_source:
                    log("Account FOUND!", "OK")
                    return "FOUND"
            
            # THIRD: Check for "not found" indicators (only after checking FOUND)
            not_found_indicators = [
                "no search results",
                "no account found",
                "we couldn't find",
                "no results",
                "لم نتمكن من العثور",
                "لا توجد نتائج",
                "لم يتم العثور",
                "try again",
                "حاول مرة أخرى",
            ]
            
            for indicator in not_found_indicators:
                if indicator in page_source:
                    log(f"Account NOT FOUND (Keyword: {indicator})", "WARN")
                    return "NOT_FOUND"
                    
            # FOURTH: Check for Profile Card (Visual element)
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, '.uiHeaderTitle') or self.driver.find_elements(By.CSS_SELECTOR, 'form[action*="recover"]'):
                     log("Account FOUND (Visual check)!", "OK")
                     return "FOUND"
            except:
                pass

            # Fallback
            log("State unsure, assuming FOUND to proceed to next check", "INFO")
            # Save debug screenshot for unsure state
            self._save_failure_snapshot("step4_unsure_state")
            return "FOUND"
            
            # If we're not sure, assume FOUND and try to continue
            log("Unknown result - assuming FOUND and continuing...", "WARN")
            return "FOUND"
            
        except Exception as e:
            log(f"Error checking account: {e}", "ERROR")
            return "ERROR"
    
    def step5_select_sms_option(self):
        """Step 5: Select SMS recovery option (NOT email)"""
        log("Step 5: Looking for SMS option (avoiding email)...")
        self._handle_cookie_consent()
        
        time.sleep(0.5)
        
        try:
            page_source = self.driver.page_source
            
            # First, check if there's a link with send_sms in href
            try:
                sms_link = self.driver.find_element(By.XPATH, "//a[contains(@href, 'send_sms')]")
                if sms_link:
                    sms_link.click()
                    log("Clicked SMS link!", "OK")
                    time.sleep(0.5)
                    return True
            except:
                pass
            
            # Look for radio button or option with phone/SMS text
            sms_keywords = ['sms', 'text', 'phone', 'mobile', 'رسالة نصية', 'هاتف', 'جوال']
            email_keywords = ['email', 'gmail', 'mail', 'بريد', 'إيميل']
            
            # Find all clickable elements
            try:
                # Look for radio buttons
                radio_buttons = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                for radio in radio_buttons:
                    try:
                        # Get parent or label text
                        parent = radio.find_element(By.XPATH, "./..")
                        parent_text = parent.text.lower()
                        
                        # Check if it's SMS related and NOT email
                        is_sms = any(kw in parent_text for kw in sms_keywords)
                        is_email = any(kw in parent_text for kw in email_keywords)
                        
                        if is_sms and not is_email:
                            radio.click()
                            log("Selected SMS radio button!", "OK")
                            time.sleep(0.3)
                            return True
                    except:
                        continue
            except:
                pass
            
            # Look for div or button with SMS text
            try:
                elements = self.driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'SMS', 'sms'), 'sms') or contains(text(), 'text message') or contains(text(), 'phone')]")
                for elem in elements:
                    elem_text = elem.text.lower()
                    is_email = any(kw in elem_text for kw in email_keywords)
                    if not is_email:
                        elem.click()
                        log("Clicked SMS option!", "OK")
                        time.sleep(0.3)
                        return True
            except:
                pass
            
            # Look specifically for phone number pattern in options
            try:
                # Find elements that contain phone number format (like +20...)
                phone_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '+') and not(contains(text(), '@'))]")
                for elem in phone_elements:
                    if '@' not in elem.text:  # Make sure it's not email
                        try:
                            elem.click()
                            log("Clicked phone number option!", "OK")
                            time.sleep(0.3)
                            return True
                        except:
                            continue
            except:
                pass
            
            log("Could not find specific SMS option - may need manual selection", "WARN")
            return False
            
        except Exception as e:
            log(f"Error searching number: {e}", "ERROR")
            self._save_failure_snapshot("step2_search_error")
            return False
    
    def step6_send_code(self):
        """Step 6: Click send code / continue button"""
        log("Step 6: Sending OTP code...")
        
        try:
            # Try clicking Continue/Send button multiple times
            button_selectors = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Continue')]"),
                (By.XPATH, "//button[contains(text(), 'Send')]"),
                (By.XPATH, "//button[contains(text(), 'متابعة')]"),
                (By.XPATH, "//button[contains(text(), 'إرسال')]"),
                (By.CSS_SELECTOR, "[data-testid='recover_nonce_next_button']"),
                (By.XPATH, "//a[contains(@href, 'recover/code')]"),
                (By.XPATH, "//button"),  # Try any button
                (By.CSS_SELECTOR, "button"),
                (By.XPATH, "//input[@type='submit']"),
                (By.CSS_SELECTOR, "[role='button']"),
            ]
            
            clicked = False
            for _ in range(3):  # Try 3 times
                for by, selector in button_selectors:
                    try:
                        buttons = self.driver.find_elements(by, selector)
                        for button in buttons:
                            try:
                                if button.is_displayed() and button.is_enabled():
                                    button.click()
                                    log(f"Clicked button: {selector}", "OK")
                                    clicked = True
                                    time.sleep(0.5)
                            except:
                                continue
                    except:
                        continue
                if clicked:
                    break
                time.sleep(0.3)
            
            # Check if code was sent
            page_source = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            success_indicators = [
                "enter code",
                "we sent",
                "code sent",
                "check your phone",
                "أدخل الرمز",
                "تم الإرسال",
            ]
            
            for indicator in success_indicators:
                if indicator in page_source:
                    log("*** OTP CODE SENT SUCCESSFULLY! ***", "SUCCESS")
                    return True
            
            if "code" in current_url:
                log("*** OTP CODE SENT! ***", "SUCCESS")
                return True
            
            log("Code may have been sent - check phone!", "OK")
            return True
            
        except Exception as e:
            log(f"Error sending code: {e}", "ERROR")
            return False
    
    def send_otp(self, phone):
        """Main function: Send OTP to phone - 3-STEP FLOW"""
        print(f"\n{'='*60}")
        print(f"{C.BOLD}{C.CYAN}   Facebook OTP - {phone}{C.END}")
        print("="*60)
        
        result = {"phone": phone, "status": "ERROR", "message": "Unknown error", "last_url": ""}
        
        try:
            # Setup browser
            if not self._setup_driver():
                result["message"] = "Failed to setup browser"
                return result
            
            # Verify proxy is working by checking IP
            try:
                self.driver.get("https://ipv4.webshare.io/")
                time.sleep(1)
                ip_text = self.driver.find_element(By.TAG_NAME, "body").text.strip()
                if ip_text:
                    log(f"Current IP: {ip_text}", "OK")
            except Exception as e:
                log(f"Could not check IP (Continuing flow): {e}", "WARN")
            
            # ========== STEP 1: Open identify page and search ==========
            log("Step 1: Opening identify page...", "INFO")
            # User requested fixed Arabic URL to avoid language switching issues
            target_url = "https://ar-ar.facebook.com/login/identify/?ctx=recover&from_login_screen=0"
            self.driver.get(target_url)
            time.sleep(3 if self.headless else 2)
            self._handle_cookie_consent()  # Ensure cookies are handled
            
            # Log current URL
            log(f"Current URL: {self.driver.current_url}", "INFO")
            
            # Find input field
            input_field = None
            input_selectors = [
                (By.ID, "identify_email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "input[type='text']"),
            ]
            
            for attempt in range(3):
                for by, selector in input_selectors:
                    try:
                        input_field = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((by, selector))
                        )
                        if input_field and input_field.is_displayed():
                            log(f"Found input using: {selector}", "OK")
                            break
                    except:
                        continue
                if input_field:
                    break
                log(f"Retry {attempt + 1}: Refreshing page...", "WARN")
                self.driver.refresh()
                time.sleep(2)
            
            if not input_field:
                result["message"] = "Could not find identify input"
                result["last_url"] = self.driver.current_url
                return result
            
            # Enter phone and search
            input_field.clear()
            input_field.send_keys(phone)
            time.sleep(2)  # Wait before pressing Enter
            
            # DEBUG: Screenshot BEFORE search
            try:
                self.driver.save_screenshot("debug_before_search.png")
                self.send_telegram_photo(f"Before Search ({phone})", "debug_before_search.png")
            except: pass

            input_field.send_keys(Keys.ENTER)
            log(f"Searching for {phone}...", "OK")
            
            # Wait for search result (Increased to 8s)
            time.sleep(8)
            
            # DEBUG: Screenshot AFTER search
            try:
                self.driver.save_screenshot("debug_after_search.png")
                self.send_telegram_photo(f"After Search ({phone})", "debug_after_search.png")
            except: pass
            
            # Log URL after search
            log(f"URL after search: {self.driver.current_url}", "INFO")
            
            # Check for POSITIVE match first (Profile card / 'Is this you')
            try:
                # Look for 'send_sms' or 'reset_password' indicators in URL
                if "recover" in self.driver.current_url or "reset" in self.driver.current_url:
                    log("Positive match by URL!", "OK")
                else:
                    # Look for profile card or specific texts
                    page_source = self.driver.page_source.lower()
                    positive_kws = ["send code", "isi koda", "sms", "text message", "whatsapp", "email", "facebook user", "is this you", "identify"]
                    if any(kw in page_source for kw in positive_kws):
                         log("Positive match by keywords!", "OK")
            except:
                pass

            # Check if GENUINELY not found
            page_source = self.driver.page_source.lower()
            
            # Stricter not found keywords
            not_found_keywords = [
                "no search results",
                "your search did not return any results",
                "didn't match any account",
                "لم نتمكن من العثور",
                "لا توجد نتائج بحث"
            ]
            
            # Only trigger NOT FOUND if we are DEFINITELY on an error page (not just loading)
            current_url = self.driver.current_url.lower()
            is_identify_page = "identify" in current_url or "login" in current_url
            
            if is_identify_page and any(kw in page_source for kw in not_found_keywords):
                # Double check: verify 'initiate' is NOT in URL (which would mean we actually succeeded)
                if "initiate" not in current_url:
                    log("Account NOT FOUND", "WARN")
                    # DEBUG: Save snapshot to understand why it wasn't found in headless
                    self._save_failure_snapshot("NOT_FOUND_debug")
                    try:
                        with open("debug_not_found.html", "w", encoding="utf-8") as f:
                            f.write(page_source)
                        log("Saved debug_not_found.html", "INFO")
                    except:
                        pass
                        
                    result["status"] = "NOT_FOUND"
                    result["message"] = "Phone not linked to Facebook"
                    result["last_url"] = self.driver.current_url
                    print(f"{C.Y}   [NOT FOUND]{C.END}")
                    print(f"   Last URL: {result['last_url']}")
                    return result
            
            log("Account FOUND! Moving to step 2...", "OK")
            
            # ========== STEP 2: Navigate to recover/initiate ==========
            log("Step 2: Opening recover/initiate page...", "INFO")
            
            # Force navigation to the specific URL requested
            recovery_url = "https://www.facebook.com/recover/initiate/?is_from_lara_screen=1"
            self.driver.get(recovery_url)
            log(f"Request sent to: {recovery_url}", "INFO")
            
            # Wait for page load
            time.sleep(3 if self.headless else 2)
            
            # Verify we are not redirected back immediately
            current_url = self.driver.current_url
            log(f"Current URL: {current_url}", "INFO")
            
            if "recover/initiate" not in current_url and "recover/code" not in current_url:
                # We were redirected back
                if "login/identify" in current_url or "login" in current_url:
                     # Check for block
                     page_source = self.driver.page_source
                     if "You're Temporarily Blocked" in page_source or "going too fast" in page_source:
                         log("!! BLOCK DETECTED (Step 2): You're Temporarily Blocked !!", "ERROR")
                         self._save_failure_snapshot("blocked_step2")
                         return {"phone": phone, "status": "BLOCKED", "message": "Rate limited at Step 2"}
                     else:
                         log("Silent redirect back to identify page in Step 2.", "WARN")
                         self._save_failure_snapshot("step2_redirect_fail")
                         # Ensure we fail here instead of proceeding to Step 3 blindly
                         pass 

            # Retry Loop for Redirect/Rate Limit (Step 3)
            max_retries = 3
            for attempt in range(max_retries):
                log(f"Step 3: Clicking Continue (Attempt {attempt+1}/{max_retries})...", "INFO")
                
                # ... (Find Button Logic - simplified re-search) ...
                continue_btn = None
                try:
                    # Specific button
                    continue_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='reset_action'][value='1']"))
                    )
                except:
                    pass
                
                if not continue_btn:
                     try:
                        continue_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "button._42ft._4jy0._9nq0"))
                        )
                     except:
                        pass
                
                if not continue_btn:
                     # Fallback to any submit
                     try:
                        continue_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                     except:
                        pass

                if continue_btn:
                    # Click Logic
                    self.random_sleep(5, 8)
                    try:
                        self.driver.execute_script("arguments[0].click();", continue_btn)
                        log(f"Continue clicked (JS) - Attempt {attempt+1}", "OK")
                    except:
                        continue_btn.click()
                        log(f"Continue clicked (Std) - Attempt {attempt+1}", "OK")
                    
                    # Wait for navigation
                    log("Waiting for navigation...", "INFO")
                    time.sleep(5)
                    
                    current_url = self.driver.current_url
                    
                    if "recover/code" in current_url:
                        log("Navigated to OTP page!", "OK")
                        return True
                    
                    elif "login/identify" in current_url:
                        # Check for specific block message
                        page_source = self.driver.page_source
                        if "You're Temporarily Blocked" in page_source or "going too fast" in page_source:
                             log("!! BLOCK DETECTED: You're Temporarily Blocked (Going too fast) !!", "ERROR")
                             self._save_failure_snapshot("blocked_temporarily")
                             return False

                        log(f"Redirected back to identify (Attempt {attempt+1}). Waiting...", "WARN")
                        time.sleep(5) # Wait before retry
                        # Don't return False yet, Try again!
                        if attempt == max_retries - 1:
                             log("!! BLOCK REASON: Rate Limit (Persistent) !!", "ERROR")
                             # DUMP HTML to find the "Why"
                             page_source = self.driver.page_source
                             self._save_failure_snapshot("redirect_loop_blocked_final")
                             return False
                        else:
                             # Refresh before retry? No, might lose state. Just re-find button.
                             pass
                    else:
                        log(f"Unknown navigation: {current_url}", "WARN")
                        # If unknown, maybe we are at OTP page but URL is weird?
                        break # Break to check commonly shared exit logic
                else:
                    log("Continue button not found on this attempt.", "WARN")
                    time.sleep(2)
            
            # Check Result outside loop (if break or retries exhausted without definite Fail)
            current_url = self.driver.current_url
            if "recover/code" in current_url:
                 return True
                
            else:
                log(f"Unknown navigation: {current_url}", "WARN")
                self._save_failure_snapshot("step3_unknown_nav")
                return False
                
        except Exception as e:
            log(f"Error clicking search: {e}", "ERROR")
            self._save_failure_snapshot("step3_click_error")
            result["last_url"] = self.driver.current_url
            log(f"Final URL: {result['last_url']}", "INFO")
            
            # Check success
            if "/recover/code" in result["last_url"] or "rm=send_sms" in result["last_url"]:
                log("*** OTP SENT SUCCESSFULLY! ***", "SUCCESS")
                result["status"] = "OTP_SENT"
                result["message"] = "OTP sent successfully"
                print(f"{C.G}{C.BOLD}   [SUCCESS] OTP sent!{C.END}")
            else:
                # Check for text confirmation in page source (AJAX update)
                page_source = self.driver.page_source.lower()
                success_keywords = ["enter code", "security code", "digit code", "we sent", "enter the code", "أدخل الرمز", "الرمز المكون", "رمز النزاع", "sent a code"]
                
                if any(kw in page_source for kw in success_keywords):
                    result["status"] = "OTP_SENT"
                    result["message"] = "OTP sent (detected via text)"
                    print(f"{C.G}   [OTP SENT] Check phone (Text Confirmed){C.END}")
                else:
                    log("Continue clicked but page didn't navigate to code page", "WARN")
                    
                    # Check if we were redirected back to identify (Failure loop)
                    if "login/identify" in self.driver.current_url:
                        result["status"] = "FAILED"
                        result["message"] = "Redirected back to identify page (Possible block)"
                        print(f"{C.R}   [FAILED] Redirected to identify page{C.END}")
                    else:
                        result["last_url"] = self.driver.current_url
                        print(f"   Last URL: {result['last_url']}")
                        return result
                
        except Exception as e:
            log(f"Error: {e}", "ERROR")
            result["message"] = str(e)
            return result
            
        except Exception as e:
            log(f"Error: {e}", "ERROR")
            result["message"] = str(e)
            return result
            
        finally:
            self._close_driver()


def format_phone(phone):
    """Format phone number"""
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if not phone.startswith('+'):
        phone = '+' + phone
    return phone


def process_single_phone(phone, headless, stats, proxy_manager=None):
    """Process a single phone number (used for parallel processing)"""
    try:
        phone = format_phone(phone)
        browser = FacebookOTPBrowser(headless=headless, proxy_manager=proxy_manager)
        result = browser.send_otp(phone)
        if result and "status" in result:
            stats.update(result["status"])
        else:
            stats.update("ERROR")
            result = {"phone": phone, "status": "ERROR", "message": "None result returned"}
        return result
    except Exception as e:
        log(f"Process error for {phone}: {e}", "ERROR")
        return {"phone": phone, "status": "ERROR", "message": str(e)}


def process_batch(filename, headless=False, parallel=False, workers=3, proxy_file=None):
    """Process multiple phone numbers from file
    
    Args:
        filename: Path to file with phone numbers
        headless: Run without visible browser
        parallel: Use parallel processing (only in headless mode)
        workers: Number of parallel workers (default 3)
        proxy_file: Path to file with proxies (optional)
    """
    # Load proxies if file provided
    proxy_manager = None
    if proxy_file:
        proxy_manager = ProxyManager(proxy_file)
    try:
        with open(filename, 'r') as f:
            phones = [line.strip() for line in f if line.strip()]
        
        total = len(phones)
        stats = Stats(total)
        results = []
        
        print(f"\n{C.BOLD}{C.CYAN}╔══════════════════════════════════════════════════════════╗{C.END}")
        print(f"{C.BOLD}{C.CYAN}║{C.END}           🚀 STARTING BATCH PROCESSING                    {C.BOLD}{C.CYAN}║{C.END}")
        print(f"{C.BOLD}{C.CYAN}╠══════════════════════════════════════════════════════════╣{C.END}")
        print(f"{C.BOLD}{C.CYAN}║{C.END}  📁 File: {filename:<45} {C.BOLD}{C.CYAN}║{C.END}")
        print(f"{C.BOLD}{C.CYAN}║{C.END}  📱 Numbers: {total:<42} {C.BOLD}{C.CYAN}║{C.END}")
        print(f"{C.BOLD}{C.CYAN}║{C.END}  🖥️  Mode: {'HEADLESS (No Browser)' if headless else 'VISIBLE (With Browser)':<38} {C.BOLD}{C.CYAN}║{C.END}")
        print(f"{C.BOLD}{C.CYAN}║{C.END}  ⚡ Parallel: {'YES (' + str(workers) + ' workers)' if parallel else 'NO (Sequential)':<40} {C.BOLD}{C.CYAN}║{C.END}")
        print(f"{C.BOLD}{C.CYAN}╚══════════════════════════════════════════════════════════╝{C.END}\n")
        
        start_time = time.time()
        
        if parallel and headless:
            # Parallel processing with ThreadPoolExecutor
            log(f"Starting parallel processing with {workers} workers...", "INFO")
            
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(process_single_phone, phone, headless, stats, proxy_manager): phone for phone in phones}
                
                for future in as_completed(futures):
                    phone = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        # Show live stats after each completion
                        stats.display()
                    except Exception as e:
                        log(f"Error processing {phone}: {e}", "ERROR")
                        stats.update("ERROR")
                        results.append({"phone": phone, "status": "ERROR", "message": str(e)})
        else:
            # Sequential processing
            for i, phone in enumerate(phones, 1):
                print(f"\n{'='*60}")
                print(f"   Processing {i}/{total}: {phone}")
                print('='*60)
                
                result = process_single_phone(phone, headless, stats, proxy_manager)
                results.append(result)
                
                # Show live stats
                stats.display()
                
                # No delay between requests in sequential mode
                pass
        
        elapsed = time.time() - start_time
        
        # Final Summary
        print(f"\n{C.BOLD}{C.G}╔══════════════════════════════════════════════════════════╗{C.END}")
        print(f"{C.BOLD}{C.G}║{C.END}              ✅ BATCH PROCESSING COMPLETE!                {C.BOLD}{C.G}║{C.END}")
        print(f"{C.BOLD}{C.G}╠══════════════════════════════════════════════════════════╣{C.END}")
        print(f"{C.BOLD}{C.G}║{C.END}  📱 Total Numbers:     {total:<10}                     {C.BOLD}{C.G}║{C.END}")
        print(f"{C.BOLD}{C.G}║{C.END}  ✓ Success (OTP Sent): {C.BOLD}{stats.success}{C.END:<10}                     {C.BOLD}{C.G}║{C.END}")
        print(f"{C.BOLD}{C.G}║{C.END}  ⚠ Not Found:          {stats.not_found:<10}                     {C.BOLD}{C.G}║{C.END}")
        print(f"{C.BOLD}{C.G}║{C.END}  ✗ Failed/Errors:      {stats.failed:<10}                     {C.BOLD}{C.G}║{C.END}")
        print(f"{C.BOLD}{C.G}║{C.END}  ⏱️  Time Elapsed:       {elapsed:.1f}s                           {C.BOLD}{C.G}║{C.END}")
        print(f"{C.BOLD}{C.G}╚══════════════════════════════════════════════════════════╝{C.END}\n")
        
        return results
        
    except FileNotFoundError:
        log(f"File not found: {filename}", "ERROR")
        return None


def main():
    print(f"""
{C.BOLD}{C.CYAN}╔════════════════════════════════════════════════════════════╗
║         Facebook OTP Browser Automation                     ║
║         Uses Real Browser - More Reliable!                  ║
║         Now with Proxy Support!                             ║
║                                                             ║
║         Designed by: Doctor Kayf (@Doc_kayf)                ║
╚════════════════════════════════════════════════════════════╝{C.END}
""")
    print("DEBUG: Inside main", flush=True)
    # Check for flags
    headless = "--headless" in sys.argv
    parallel = "--parallel" in sys.argv
    
    # Check for proxy file
    proxy_file = None
    for i, arg in enumerate(sys.argv):
        if arg == "--proxy" and i + 1 < len(sys.argv):
            proxy_file = sys.argv[i + 1]
            break
    
    # Filter out flags and their values
    args = []
    skip_next = False
    for i, a in enumerate(sys.argv[1:]):
        if skip_next:
            skip_next = False
            continue
        if a == "--proxy":
            skip_next = True
            continue
        if a not in ["--headless", "--parallel"]:
            args.append(a)
    
    if len(args) < 1:
        print(f"""
{C.Y}Usage:{C.END}
    python fb_otp_browser.py <phone_number>
    python fb_otp_browser.py <file.txt>
    python fb_otp_browser.py <phone_number> --headless
    python fb_otp_browser.py <file.txt> --headless --parallel
    python fb_otp_browser.py <file.txt> --proxy proxies.txt

{C.Y}Options:{C.END}
    --headless     Run without visible browser
    --parallel     Process multiple numbers in parallel (headless only)
    --proxy FILE   Use proxies from file (rotates for each number)

{C.Y}Examples:{C.END}
    python fb_otp_browser.py +201234567890
    python fb_otp_browser.py numbers.txt --proxy proxies.txt
    python fb_otp_browser.py numbers.txt --headless --parallel --proxy proxies.txt  {C.G}(FAST!){C.END}

{C.Y}Proxy File Format:{C.END}
    # Each line: host:port:username:password (or just host:port for no auth)
    unblock.oxylabs.io:60000:user:pass
    1.2.3.4:8080
""")
        phone = input("Enter phone number: ").strip()
        if not phone:
            return
    else:
        phone = args[0]
    
    # Show proxy status
    if proxy_file:
        print(f"{C.B}[INFO] Proxy file: {proxy_file}{C.END}")
    
    # Check if file (batch mode)
    if phone.endswith('.txt'):
        process_batch(phone, headless=headless, parallel=parallel, proxy_file=proxy_file)
    else:
        phone = format_phone(phone)
        proxy_manager = ProxyManager(proxy_file) if proxy_file else None
        browser = FacebookOTPBrowser(headless=headless, proxy_manager=proxy_manager)
        result = browser.send_otp(phone)
        print(f"\nResult: {result}")


if __name__ == '__main__':
    main()
