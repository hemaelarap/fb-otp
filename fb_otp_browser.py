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
    print("[WARNING] selenium-wire not installed. Proxy auth may not work. Run: pip install selenium-wire")

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("[WARNING] webdriver-manager not installed. Run: pip install webdriver-manager")
    ChromeDriverManager = None

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
        self.wait_time = 10
        self.proxy = proxy
        self.proxy_manager = proxy_manager
        
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
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--ignore-ssl-errors")
        
        # Realistic user agent
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        # Disable automation flags
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
            if ChromeDriverManager:
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
            
            # Execute script to hide webdriver
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
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
    
    def step1_open_recovery_page(self):
                
        except Exception as e:
            log(f"Error loading page: {e}", "ERROR")
            return False
    
    def step2_enter_phone(self, phone):
        """Step 2: Enter phone number in search field"""
        log(f"Step 2: Entering phone number: {phone}...")
        
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
            ]
            
            for indicator in not_found_indicators:
                if indicator in page_source:
                    log("Account NOT FOUND", "WARN")
                    return "NOT_FOUND"
            
            # If we're not sure, assume FOUND and try to continue
            log("Unknown result - assuming FOUND and continuing...", "WARN")
            return "FOUND"
            
        except Exception as e:
            log(f"Error checking account: {e}", "ERROR")
            return "ERROR"
    
    def step5_select_sms_option(self):
        """Step 5: Select SMS recovery option (NOT email)"""
        log("Step 5: Looking for SMS option (avoiding email)...")
        
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
            log(f"Error selecting SMS: {e}", "ERROR")
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
            except:
                pass
            
            # ========== STEP 1: Open identify page and search ==========
            log("Step 1: Opening identify page...", "INFO")
            self.driver.get("https://www.facebook.com/login/identify")
            time.sleep(3 if self.headless else 2)
            
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
            input_field.send_keys(Keys.ENTER)
            log(f"Searching for {phone}...", "OK")
            
            # Wait for search result (Increased to 6s + check for 'Is this you' element)
            time.sleep(6)
            
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
            log(f"Navigated to: {recovery_url}", "OK")
            
            # Wait for page load
            time.sleep(3 if self.headless else 2)
            
            # Log current URL
            log(f"Current URL: {self.driver.current_url}", "INFO")
            
            # Log current URL
            log(f"Current URL: {self.driver.current_url}", "INFO")
            
            # ========== STEP 3: Click Continue button ==========
            log("Step 3: Looking for Continue button...", "INFO")
            
            # Wait for page to fully load
            time.sleep(2)
            
            continue_btn = None
            
            # Try the specific Continue button first
            try:
                continue_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button[name='reset_action'][value='1']"))
                )
                log("Found Continue button (reset_action)", "OK")
            except:
                pass
            
            # Try by class
            if not continue_btn:
                try:
                    continue_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "button._42ft._4jy0._9nq0"))
                    )
                    log("Found Continue button (class)", "OK")
                except:
                    pass
            
            # Try any submit button
            if not continue_btn:
                try:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
                    for btn in btns:
                        if btn.is_displayed():
                            continue_btn = btn
                            log("Found submit button", "OK")
                            break
                except:
                    pass

            # Try text-based search (Robust fallback)
            if not continue_btn:
                try:
                    keywords = ["continue", "mencoba", "next", "send", "sms", "متابعة", "رقم", "إرسال", "استمرار", "تالي"]
                    for kw in keywords:
                        try:
                            # XPath to find button/a/div with text containing keyword (case-insensitive)
                            xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw}')]"
                            elements = self.driver.find_elements(By.XPATH, xpath)
                            for elem in elements:
                                if elem.is_displayed() and elem.is_enabled():
                                    tag = elem.tag_name.lower()
                                    # Filter for likely clickable elements
                                    if tag in ['button', 'a'] or elem.get_attribute('role') == 'button':
                                        continue_btn = elem
                                        log(f"Found button by text: '{kw}' ({tag})", "OK")
                                        break
                            if continue_btn:
                                break
                        except:
                            continue
                except:
                    pass
            
            if continue_btn:
                # Scroll into view first
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", continue_btn)
                time.sleep(1)
                
                # Check current URL before clicking
                current_url_before = self.driver.current_url
                
                # Attempt 1: ActionChains (Mouse Move + Click)
                try:
                    from selenium.webdriver.common.action_chains import ActionChains
                    actions = ActionChains(self.driver)
                    actions.move_to_element(continue_btn).pause(0.5).click().perform()
                    log("Continue clicked (ActionChains)!", "OK")
                except Exception as e:
                    log(f"ActionChains click failed: {str(e)}", "WARN")
                    # Attempt 2: Standard Click
                    try:
                        continue_btn.click()
                        log("Continue clicked (Standard)!", "OK")
                    except:
                        # Attempt 3: JS Click
                        self.driver.execute_script("arguments[0].click();", continue_btn)
                        log("Continue clicked (JS)!", "OK")
                
                # Wait for page navigation with retry
                log("Waiting for page to navigate...", "INFO")
                
                # Monitor URL change loop
                navigated = False
                for _ in range(10): # Wait up to 10 seconds
                    time.sleep(1)
                    if self.driver.current_url != current_url_before:
                        navigated = True
                        break
                    # If not navigated, try clicking again with JS as last resort
                    if _ == 4: # After 4 seconds
                         log("Navigation took too long, retrying JS click...", "WARN")
                         try:
                             self.driver.execute_script("arguments[0].click();", continue_btn)
                             log("Retry click sent, waiting 2s...", "INFO")
                             time.sleep(2)
                         except:
                             pass

                if not navigated and self.headless:
                    # In headless mode on GitHub Actions, sometimes we need to hit Enter on the button
                    try:
                        continue_btn.send_keys(Keys.ENTER)
                        log("Sent ENTER key to button", "INFO")
                        time.sleep(3)
                    except:
                        pass
                
                # Wait up to 10 more seconds for /recover/code/
                for i in range(10):
                    current_url = self.driver.current_url
                    if "/recover/code" in current_url or "rm=send_sms" in current_url:
                        log(f"Navigated to OTP page!", "OK")
                        break
                    time.sleep(1)
                
                # Get final URL
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
                            # Original fallback for unknown pages
                            result["status"] = "OTP_SENT"
                            result["message"] = "Continue clicked, unknown result state"
                            print(f"{C.Y}   [LIKELY SENT] Check phone (Unknown State){C.END}")
                
                print(f"   Last URL: {result['last_url']}")
                return result
            else:
                log("Continue button not found!", "ERROR")
                result["status"] = "FOUND_NO_OTP"
                result["message"] = "Account found but Continue button not found"
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
    phone = format_phone(phone)
    browser = FacebookOTPBrowser(headless=headless, proxy_manager=proxy_manager)
    result = browser.send_otp(phone)
    stats.update(result["status"])
    return result


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
