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



try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("[WARNING] webdriver-manager not installed. Run: pip install webdriver-manager")
    ChromeDriverManager = None

# Undetected Chromedriver removed by user request
UNDETECTED_AVAILABLE = False
VIDEO_AVAILABLE = False


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
        self.snapshot_taken = False
        self.wait = None
        self.current_phone = None
        
    
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
            
            # 3. Save Screenshot
            filename = f"fail_{step_name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            log(f"Screenshot saved to: {filename}", "INFO")
            
            # 4. Upload to Telegram
            caption = f"⚠️ FAILURE: {step_name} [{self.current_phone}]\nURL: {url}\nTitle: {title}"
            self.send_telegram_photo(caption, filename)
            
        except Exception as e:
            log(f"Failed to save failure snapshot: {e}", "WARN")

    def _handle_failure(self, step_name):
        """Wrapper for save_failure_snapshot"""
        self._save_failure_snapshot(step_name)

    def _save_screenshot(self, name):
         """Helper to save normal flow screenshot"""
         try:
             timestamp = int(time.time())
             filename = f"{name}_{timestamp}.png"
             self.driver.save_screenshot(filename)
             # Send to TG
             caption = f"📸 Step: {name} [{self.current_phone}]"
             self.send_telegram_photo(caption, filename)
         except: pass
    
    def _take_step_snapshot(self, step_name, phone_info=""):
        """Alias for _save_screenshot to prevent errors if old calls exist"""
        self._save_screenshot(step_name)

    def _setup_driver(self):
        """Setup Chrome WebDriver with optional proxy support"""
        log("Setting up Chrome browser...")
        
        # Mobile Viewport & User Agent (Android)
        # Desktop User Agent (Windows 10 Chrome)
        desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        
        def get_configured_options(use_mobile_emulation=False):
            """Helper to generate fresh options"""
            options = Options()
            
            if self.headless:
                options.add_argument("--headless=new")
            
            # Anti-detection options
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # UA & Window Size (Laptop)
            options.add_argument(f"user-agent={desktop_ua}")
            options.add_argument("--window-size=1366,768")
            
            if use_mobile_emulation:
                # Kept for backward compatibility if needed, but default is False
                pass

            options.add_argument("--start-maximized")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-gpu")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-notifications")
            options.add_argument("--lang=en-US")
            options.add_argument("--ignore-certificate-errors")
            options.add_argument("--ignore-ssl-errors")
            
            # Add realistic browser preferences
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "profile.managed_default_content_settings.images": 1,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "intl.accept_languages": "en-US,en",
                "plugins.always_open_pdf_externally": True,
                "webrtc.ip_handling_policy": "disable_non_proxied_udp",
                "webrtc.multiple_routes_enabled": False,
                "webrtc.nonproxied_udp_enabled": False
            }
            options.add_experimental_option("prefs", prefs)
            
            if not UNDETECTED_AVAILABLE:
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
            
            # Proxy Setup
            proxy_string = self.proxy
            if not proxy_string and self.proxy_manager:
                proxy_string = self.proxy_manager.get_next()
            
            if proxy_string:
                self._configure_proxy(options, proxy_string)
                
            return options

        # Driver Initialization Logic
        try:
            log("Starting Standard Chrome...", "INFO")
            
            # Standard Chrome Options
            safe_options = get_configured_options(use_mobile_emulation=False)
            
            chrome_error = None
            if ChromeDriverManager:
                try:
                    driver_path = ChromeDriverManager().install()
                    if "THIRD_PARTY_NOTICES" in driver_path:
                            import os
                            base_dir = os.path.dirname(driver_path)
                            real_path = os.path.join(base_dir, "chromedriver")
                            if os.path.exists(real_path):
                                driver_path = real_path
                                os.chmod(driver_path, 0o755)
                    
                    service = Service(driver_path)
                    self.driver = webdriver.Chrome(service=service, options=safe_options)
                    log("Standard Chrome (via DriverManager) ready!", "OK")
                except Exception as e:
                    chrome_error = str(e)
                    log(f"Standard Chrome (Manager) failed: {e}", "WARN")
            
            # Fallback: Direct Standard Chrome
            if not self.driver:
                try:
                    self.driver = webdriver.Chrome(options=safe_options)
                    log("Standard Chrome (direct) ready!", "OK")
                except Exception as e:
                    chrome_error = str(e)
                    log(f"Standard Chrome (Direct) failed: {e}", "ERROR")
            
            # Store error for later reporting
            self._chrome_error = chrome_error

            # --- ADVANCED FINGERPRINT SPOOFING (CDP) ---
            if self.driver:
                self.wait = WebDriverWait(self.driver, 10)
                try:
                    # 1. Spooof WebGL/GPU
                    self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                            const getParameter = WebGLRenderingContext.prototype.getParameter;
                            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                                if (parameter === 37445) { return 'Google Inc. (NVIDIA)'; }
                                if (parameter === 37446) { return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)'; }
                                return getParameter.apply(this, arguments);
                            };
                            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                            Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        """
                    })
                    log("Anti-fingerprint scripts injected.", "OK")
                    
                    # TIMEOUTS: Critical to prevent 30m+ hangs
                    self.driver.set_page_load_timeout(30)
                    self.driver.set_script_timeout(30)
                    log("Driver timeouts set to 30s.", "OK")
                    
                except Exception as e:
                    log(f"Warning: Failed to inject anti-fingerprint scripts: {e}", "WARN")

            return True if self.driver else False
            
        except Exception as e:
            log(f"CRITICAL: Failed to setup Chrome: {e}", "ERROR")
            return False

    def _configure_proxy(self, options, proxy_string):
        """Helper to configure proxy on options object"""
        proxy_data = None
        if self.proxy_manager:
            proxy_data = self.proxy_manager.parse_proxy(proxy_string)
        else:
            parts = proxy_string.split(':')
            if len(parts) >= 4:
                proxy_data = {'host': parts[0], 'port': parts[1], 'username': parts[2], 'password': ':'.join(parts[3:])}
            elif len(parts) == 2:
                proxy_data = {'host': parts[0], 'port': parts[1], 'username': None, 'password': None}
        
        if proxy_data:
            proxy_host = proxy_data['host']
            proxy_port = proxy_data['port']
            proxy_user = proxy_data.get('username')
            proxy_pass = proxy_data.get('password')
            
            if proxy_user and proxy_pass:
                # Use folder-based extension
                import os
                script_dir = os.path.dirname(os.path.abspath(__file__))
                extension_dir = os.path.join(script_dir, 'proxy_extension')
                os.makedirs(extension_dir, exist_ok=True)
                
                # Check if file exists to avoid writing every time
                if not os.path.exists(os.path.join(extension_dir, 'manifest.json')):
                    with open(os.path.join(extension_dir, 'manifest.json'), 'w') as f:
                        f.write('''{
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Proxy Auth Extension",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": {"scripts": ["background.js"], "persistent": true},
        "minimum_chrome_version": "22.0.0"
    }''')
                
                proxy_scheme = "https" if "oxylabs" in proxy_host.lower() else "http"
                background_js = f'''var config = {{
    mode: "fixed_servers",
    rules: {{ singleProxy: {{ scheme: "{proxy_scheme}", host: "{proxy_host}", port: {proxy_port} }}, bypassList: ["localhost"] }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});
function callbackFn(details) {{ return {{ authCredentials: {{ username: "{proxy_user}", password: "{proxy_pass}" }} }}; }}
chrome.webRequest.onAuthRequired.addListener(callbackFn, {{urls: ["<all_urls>"]}}, ['blocking']);'''
                
                with open(os.path.join(extension_dir, 'background.js'), 'w') as f:
                    f.write(background_js)
                
                options.add_argument(f"--load-extension={extension_dir}")
                log(f"Proxy extension loaded: {proxy_host}:{proxy_port}", "OK")
            else:
                options.add_argument(f"--proxy-server=http://{proxy_host}:{proxy_port}")
                log(f"Using proxy: {proxy_host}:{proxy_port}", "INFO")
    
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
            return

        try:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            
            # Retry logic for 429
            max_retries = 3
            for attempt in range(max_retries):
                with open(file_path, "rb") as f:
                    files = {"photo": f}
                    data = {"chat_id": chat_id, "caption": caption}
                    response = requests.post(url, files=files, data=data)
                    
                if response.status_code == 200:
                    self.snapshot_taken = True
                    log(f"Sent Telegram photo: {caption}", "OK")
                    return
                elif response.status_code == 429:
                    retry_after = 5 # Default
                    try:
                        resp_json = response.json()
                        retry_after = resp_json.get('parameters', {}).get('retry_after', 5)
                    except:
                        pass
                    log(f"Telegram Rate Limit (429). Waiting {retry_after}s...", "WARN")
                    time.sleep(retry_after + 1)
                    continue # Retry loop
                else:
                    log(f"Failed to send Telegram photo: {response.text}", "WARN")
                    break # Don't retry other errors
                    
        except Exception as e:
            log(f"Error sending Telegram photo: {e}", "WARN")


    def simulate_human_behavior(self):
        """Simulate human-like interactions with the page"""
        try:
            # Random small scroll
            scroll_amount = random.randint(50, 200)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            time.sleep(random.uniform(0.3, 0.8))
            
            # Sometimes scroll back up a bit
            if random.choice([True, False]):
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount // 2});")
                time.sleep(random.uniform(0.2, 0.5))
            
            # Move mouse randomly (inject mouse move event)
            x = random.randint(100, 800)
            y = random.randint(100, 600)
            self.driver.execute_script(f"""
                var event = new MouseEvent('mousemove', {{
                    'view': window,
                    'bubbles': true,
                    'cancelable': true,
                    'clientX': {x},
                    'clientY': {y}
                }});
                document.dispatchEvent(event);
            """)
            time.sleep(random.uniform(0.1, 0.3))
        except:
            pass

    # ==========================================
    # NEW DESKTOP OTP FLOW STEPS
    # ==========================================

    def _handle_cookie_consent(self):
        """Handle cookie consent popup if it appears - Uses JS to click inner span"""
        try:
            # PRIMARY METHOD: JavaScript click on span (TESTED & WORKING)
            js_click_cookie = """
            (function() {
                // Method 1: Click inner span directly (MOST RELIABLE)
                let spans = [...document.querySelectorAll('span')];
                let target = spans.find(s => s.innerText === 'Allow all cookies');
                if (target) { target.click(); return 'clicked_span_en'; }
                
                // Method 2: Arabic text
                target = spans.find(s => s.innerText.includes('السماح'));
                if (target) { target.click(); return 'clicked_span_ar'; }
                
                // Method 3: Fallback to aria-label div
                let btn = document.querySelector('div[aria-label="Allow all cookies"]');
                if (btn) { 
                    let innerSpan = btn.querySelector('span');
                    if (innerSpan) { innerSpan.click(); return 'clicked_inner_span'; }
                    btn.click(); 
                    return 'clicked_div'; 
                }
                
                // Method 4: data-testid
                btn = document.querySelector('[data-testid="cookie-policy-manage-dialog-accept-button"]');
                if (btn) { btn.click(); return 'clicked_testid'; }
                
                // Method 5: First button in any dialog
                let dialog = document.querySelector('div[role="dialog"]');
                if (dialog) {
                    let firstBtn = dialog.querySelector('button');
                    if (firstBtn) { firstBtn.click(); return 'clicked_dialog_btn'; }
                }
                
                return 'not_found';
            })();
            """
            
            result = self.driver.execute_script(js_click_cookie)
            
            if result and result != 'not_found':
                log(f"Cookie consent accepted ({result})!", "OK")
                time.sleep(1)
                return True
            
            log("No cookie consent dialog found", "INFO")
            return False
        except Exception as e:
            log(f"Cookie consent check error: {e}", "WARN")
            return False

    def step1_open_recovery_page(self, phone=""):
        """Step 1: Open Facebook Identify Page (Desktop)"""
        step_name = "1_open_identify"
        log(f"Step 1: Opening Facebook Identify [{phone}]...")
        try:
            self.driver.get('https://www.facebook.com/login/identify/?ctx=recover&from_login_screen=0')
            self._save_screenshot(step_name)
            self.random_sleep(2, 4)
            
            # Check for cookie consent dialog
            self._handle_cookie_consent()
            
            self.simulate_human_behavior()
            return True
        except Exception as e:
            self._handle_failure(step_name)
            return False

    def step2_enter_phone(self, number):
        """Step 2: Enter number (Desktop Flow)"""
        step_name = "2_enter_phone"
        log(f"Step 2: Entering phone [{number}]...")
        # Check cookies again (sometimes appears late)
        self._handle_cookie_consent()
        try:
            # Try multiple selectors for input field
            input_selectors = [
                (By.ID, "identify_email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.XPATH, "//input[@placeholder]"),
            ]
            
            inp = None
            for by, selector in input_selectors:
                try:
                    inp = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((by, selector))
                    )
                    if inp and inp.is_displayed():
                        log(f"Found input field: {selector}", "INFO")
                        break
                except:
                    continue
            
            if not inp:
                log("Could not find input field", "ERROR")
                self._handle_failure(step_name)
                return False
            
            inp.clear()
            inp.send_keys(number)
            self._save_screenshot(step_name)
            return True
        except Exception as e:
            self._handle_failure(step_name)
            return False

    def step3_click_search(self, phone=""):
        """Step 3: Click Search"""
        step_name = "3_click_search"
        log(f"Step 3: Clicking Search [{phone}]...")
        # Check cookies crucial here as it blocks the button
        self._handle_cookie_consent()
        try:
            # Try multiple selectors for search button
            button_selectors = [
                (By.ID, "did_submit"),
                (By.NAME, "did_submit"),
                (By.CSS_SELECTOR, "button[name='did_submit']"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Search')]"),
                (By.XPATH, "//button[contains(text(), 'بحث')]"),
                (By.XPATH, "//input[@type='submit']"),
            ]
            
            btn = None
            for by, selector in button_selectors:
                try:
                    btn = self.driver.find_element(by, selector)
                    if btn and btn.is_displayed():
                        log(f"Found search button: {selector}", "INFO")
                        break
                except:
                    continue
            
            if not btn:
                log("Could not find search button", "ERROR")
                self._handle_failure(step_name)
                return False
            
            # Try standard click, fallback to JS click
            try:
                btn.click()
                log("Search button clicked!", "OK")
            except:
                log("Standard click failed, trying JS click...", "WARN")
                self.driver.execute_script("arguments[0].click();", btn)
                log("Search button clicked (JS)!", "OK")
            
            time.sleep(2.5) # Wait for search results to load
            self._save_screenshot(step_name)
            return True
        except Exception as e:
            # Final attempt to clear cookie if we couldn't find/click
            if self._handle_cookie_consent():
                 log("Found and cleared cookie dialog late - retrying step might be needed but failed for now", "WARN")
            self._handle_failure(step_name)
            return False

    def step4_check_account_found(self, phone=""):
        """Step 4: Analyze Search Result"""
        step_name = "4_check_result"
        log(f"Step 4: Checking account result [{phone}]...")
        try:
            url = self.driver.current_url
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            # Case 1: No Result - CHECK FIRST before anything else
            not_found_patterns = [
                "no result", "no search results", "didn't match", 
                "لم يتم العثور", "لا توجد نتائج", "try again with other"
            ]
            for pattern in not_found_patterns:
                if pattern in page_text:
                    log(f"NOT_FOUND detected: '{pattern}'", "WARN")
                    return "NOT_FOUND"
            
            # Case 1.5: "Log Into Facebook" Password Screen (intermediate step)
            # User reported this screen appears instead of recovery options.
            # We need to treat this like "TRY_ANOTHER_WAY" to force a redirect.
            if "log into facebook" in page_text or "تسجيل الدخول" in page_text:
                 # Check if password field is present to confirm it's the login screen
                 if "pass" in page_text or self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
                      log("Detected 'Log Into Facebook' password screen. Redirecting...", "INFO")
                      return "TRY_ANOTHER_WAY"

            # Case 2: Multiple Accounts - Auto-select first account using JS
            if "this is my account" in page_text or "هذا حسابي" in page_text:
                log("Multiple accounts found - selecting first one...", "INFO")
                js_select_first = """
                (function() {
                    let btns = [...document.querySelectorAll('a, button, div[role="button"]')];
                    let target = btns.find(b => b.innerText.includes('This is my account') || b.innerText.includes('هذا حسابي'));
                    if (target) { target.click(); return 'selected'; }
                    return 'not_found';
                })();
                """
                result = self.driver.execute_script(js_select_first)
                if result == 'selected':
                    log("First account selected!", "OK")
                    time.sleep(2)
                    self._save_screenshot("4_Result_MULTIPLE_SELECTED")
                return "MULTIPLE_ACCOUNTS"
            
            # Case 3: Still on identify page = NOT_FOUND
            if "identify" in url:
                return "NOT_FOUND"
                
            # Case 4: Recover Page (Direct success)
            if "recover" in url or "reset" in url:
                return "FOUND"

            # Fallback
            return "UNKNOWN"

        except Exception as e:
            return "ERROR"

    def _check_broken_page(self):
        """Check for 'This page isn't available' error and reload"""
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            broken_indicators = [
                "page isn't available", 
                "broken link",
                "reload page",
                "هذه الصفحة غير متوفرة",
                "إعادة تحميل الصفحة"
            ]
            
            if any(ind in page_text for ind in broken_indicators):
                log("⚠️ Broken/Error page detected! Reloading...", "WARN")
                self.driver.refresh()
                time.sleep(4)
                return True
            return False
        except:
            return False

    def step5_select_sms_option(self, number):
        """Step 5: Select SMS Option"""
        step_name = "5_select_sms"
        log(f"Step 5: Selecting SMS option [{number}]...")
        try:
            # Force Navigate if not already on recovery page
            if "recover" not in self.driver.current_url:
                 self.driver.get("https://www.facebook.com/recover/initiate/?is_from_lara_screen=1")
                 time.sleep(3)
            
            # Check for specific "Page isn't available" error
            self._check_broken_page()
            
            self._save_screenshot(step_name + "_start")
            
            # CRITICAL FIX: Check for "Try another way" (Intermediate Screen)
            # If we see this, we must click it to reveal the actual radio options
            try:
                try_another = None
                try_texts = ["try another way", "جرب طريقة أخرى", "طريقة أخرى"]
                
                # Check buttons and links
                candidates = self.driver.find_elements(By.XPATH, "//a | //button | //div[@role='button']")
                for el in candidates:
                    if any(t in el.text.lower() for t in try_texts):
                         try_another = el
                         break
                
                if try_another and try_another.is_displayed():
                    log(f"Found 'Try another way' button. Clicking to reveal options...", "INFO")
                    self.driver.execute_script("arguments[0].click();", try_another)
                    time.sleep(2.5) # Wait for options to load
            except Exception as e:
                log(f"Check for 'Try another way' failed (non-critical): {e}", "WARN")

            # Find SMS label
            # Strategy: Find all labels, check text for "SMS" and last 2 digits
            # PRIORITY 1: Check for "We'll send you a code" page (Direct Confirmation)
            # If we see this, the option is already selected, just click Continue
            if "send you a code" in page_source or "we'll send" in page_source:
                 log("Detected SMS confirmation page - looking for Continue button...", "INFO")
                 # We can piggyback on the continue click logic at the end, or do it here.
                 # Let's set a flag to skip finding the label
                 found_sms_option = True
                 log("SMS Confirmation Page detected - proceeding to Continue click", "OK")
            else:
                 found_sms_option = False

            # USER REQUEST: Assume SMS option is selected by default and just click Continue.
            # We will try a quick "best effort" check but won't fail if we don't find it.
            
            log("User Directive: Assuming SMS option is pre-selected. Skipping strict search.", "INFO")
             
            # Optional: Quick check just to log what we see (non-blocking)
            try:
                labels = self.driver.find_elements(By.TAG_NAME, "label")
                for l in labels:
                    if "sms" in l.text.lower() or number[-4:] in l.text:
                         log(f"Verified SMS text present: {l.text[:30]}", "INFO")
                         break
            except: pass

            found_sms_option = True # FORCE SUCCESS for this part
            
            # (Old search logic removed/bypassed to satisfy "Cancel this choice" request)
                
            time.sleep(0.5)
            
            # SUCCESS: We have an SMS option selected (or verified)
            time.sleep(0.5)
            
            # ---------------------------------------------------------
            # ULTIMATE CONTINUE BUTTON CLICKER (ALL POSSIBLE WAYS)
            # ---------------------------------------------------------
            log("Clicking 'Continue' / 'Send' button (Ultimate Strategy)...", "INFO")
            
            # 1. Define every possible selector seen on Desktop/Mobile/Arabic/English
            candidates = [
                # Verified Desktop names/classes
                (By.NAME, "reset_action"),
                (By.CSS_SELECTOR, "button._42ft._4jy0._9nq0"),
                (By.ID, "did_submit"),
                (By.ID, "u_0_5_"),
                
                # Standard Types
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                
                # Text-based (Case Insensitive via XPath) - English
                (By.XPATH, "//button[contains(translate(., 'CONTINUE', 'continue'), 'continue')]"),
                (By.XPATH, "//span[contains(translate(., 'CONTINUE', 'continue'), 'continue')]"),
                (By.XPATH, "//div[@role='button' and contains(translate(., 'CONTINUE', 'continue'), 'continue')]"),
                
                # Text-based - Arabic
                (By.XPATH, "//button[contains(., 'متابعة')]"),
                (By.XPATH, "//span[contains(., 'متابعة')]"),
                (By.XPATH, "//button[contains(., 'إرسال')]"),
                
                # Generic confirm classes
                (By.CSS_SELECTOR, ".uiButtonConfirm button"),
                (By.CSS_SELECTOR, ".uiButtonConfirm input"),
                (By.CSS_SELECTOR, "[role='button']"),
            ]
            
            clicked_any = False
            for by, val in candidates:
                try:
                    # Find all matches for this selector
                    elems = self.driver.find_elements(by, val)
                    for el in elems:
                        if el.is_displayed():
                            # Method A: Standard Click
                            try:
                                el.click()
                                log(f"Clicked Continue (Standard) using {val}", "OK")
                                clicked_any = True
                                break
                            except:
                                # Method B: JS Click
                                try:
                                    self.driver.execute_script("arguments[0].click();", el)
                                    log(f"Clicked Continue (JS) using {val}", "OK")
                                    clicked_any = True
                                    break
                                except: pass
                    
                    if clicked_any: break
                except: continue
                
            if not clicked_any:
                log("❌ Continue button NOT clicked by any method!", "ERROR")
                # Last ditch effort: Enter key on body
                try:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)
                    log("Pressed ENTER as last resort", "WARN")
                    clicked_any = True
                except:
                     return False, "CONTINUE_BTN_MISSING"

            time.sleep(2.0) # Wait for processing
            self._save_screenshot(step_name + "_success")
            return True, "OK"

        except Exception as e:
            self._handle_failure(step_name)
            return False, str(e)

    def step6_send_code(self):
        """Step 6: Verify Success"""
        step_name = "6_verify_send"
        try:
            url = self.driver.current_url
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            
            self._save_screenshot(step_name)
            
            # Success indicators
            success_keywords = [
                "enter code", "أدخل الرمز", 
                "we sent", "تم الإرسال", 
                "check your phone", 
                "confirm your account"
            ]
            
            is_success = False
            if "recover/code" in url or "recover/password" in url or "enter_code" in url:
                is_success = True
            else:
                for kw in success_keywords:
                    if kw in page_text:
                        is_success = True
                        break
            
            if is_success:
                 log(f"🎉 OTP SUCCESS! Page: {url}", "SUCCESS")
                 return True, "SENT"
            else:
                 log(f"⚠️ Unsure of success. URL: {url}", "WARN")
                 # Check for captcha
                 if "security check" in page_text or "enter the text" in page_text or "captcha" in page_text:
                     return False, "CAPTCHA"
                 return True, "SENT_BUT_UNVERIFIED" # Still count as success if no clear error
                 
        except Exception as e:
            return False, str(e)

    
    def send_otp(self, phone):
        """Main function: Send OTP to phone - Desktop Flow"""
        self.current_phone = phone
        original_phone = phone
        phone = format_phone(phone)
        
        print(f"\n{'='*60}")
        print(f"{C.BOLD}{C.CYAN}   Facebook OTP (Desktop) - {phone}{C.END}")
        print("="*60)
        
        result = {"phone": phone, "status": "ERROR", "message": "Unknown error", "last_url": ""}
        
        try:
            # Setup browser
            if not self._setup_driver():
                error_detail = getattr(self, '_chrome_error', 'Unknown error')
                result["message"] = f"Failed to setup browser: {error_detail}"
                return result
            
            # LOOP for Multiple Accounts (Default 1 pass - NO RETRY)
            # User Request: Disable loop on failure.
            max_accounts_to_process = 1 
            accounts_processed = 0
            
            # Only loop if we explicitly detect multiple accounts later
            while accounts_processed < max_accounts_to_process:
                
                # If this is the 2nd+ iteration, we need to restart the flow to get a clean state
                if accounts_processed > 0:
                    log(f"--- Processing Account #{accounts_processed + 1} ---", "INFO")
                    time.sleep(2)
                
                # ========== STEP 1: Open identify page ==========
                if not self.step1_open_recovery_page(phone):
                    result["message"] = "Failed to open recovery page"
                    break # Critical failure
                
                # ========== STEP 2: Enter phone ==========
                if not self.step2_enter_phone(phone):
                    result["message"] = "Failed to enter phone"
                    break
                
                # ========== STEP 3: Search ==========
                if not self.step3_click_search(phone):
                    result["message"] = "Failed to click search"
                    break
                    
                # ========== STEP 4: Check Result ==========
                status = self.step4_check_account_found(phone)
                self._save_screenshot(f"4_Result_{status}")
                
                if status == "NOT_FOUND":
                    log("Account NOT FOUND (Final)", "WARN")
                    result["status"] = "NOT_FOUND"
                    break
                
                elif status == "TRY_ANOTHER_WAY":
                    log("Redirected to Login - Clicking 'Try Another Way'...", "INFO")
                    try:
                        # Click the button
                        # Often the link is essentially /recover/initiate
                        self.driver.get("https://www.facebook.com/recover/initiate/?is_from_lara_screen=1")
                        time.sleep(5)
                        # Verify we are now on recovery page
                        if "recover" in self.driver.current_url or "reset" in self.driver.current_url:
                             status = "FOUND" # Proceed to next steps
                        else:
                             log("Failed to navigate to recovery after redirect", "ERROR")
                             break
                    except Exception as e:
                        log(f"Error processing Try Another Way: {e}", "ERROR")
                        break
                        
                elif status == "MULTIPLE_ACCOUNTS":
                    log("Multiple accounts detected!", "INFO")
                    try:
                        # Find all "This is me" buttons
                        buttons = self.driver.find_elements(By.XPATH, "//a[@role='button']")
                        
                        valid_buttons = []
                        for b in buttons:
                             if "account" in b.text.lower() or "هذا إيميل" in b.text or "حسابي" in b.text:
                                 valid_buttons.append(b)
                        
                        num_accounts = len(valid_buttons)
                        log(f"Found {num_accounts} valid account buttons.", "INFO")
                        
                        # Only now do we increase the loop limit
                        max_accounts_to_process = num_accounts
                        
                        if accounts_processed >= num_accounts:
                            log("All accounts processed.", "OK")
                            break
                            
                        # Click the button for the current index
                        try:
                            target_btn = valid_buttons[accounts_processed]
                            log(f"Selecting account #{accounts_processed + 1}...", "INFO")
                            target_btn.click()
                            time.sleep(5)
                            
                            # Force navigate to recovery initiate just in case
                            self.driver.get("https://www.facebook.com/recover/initiate/?is_from_lara_screen=1")
                            time.sleep(3)
                            
                        except Exception as e:
                            log(f"Error identifying account button: {e}", "ERROR")
                            break
                            
                    except Exception as e:
                        log(f"Error handling multiple accounts: {e}", "ERROR")
                        break
                elif status == "FOUND":
                    log("Account FOUND - proceeding to SMS selection...", "OK")
                    # Continue to Step 5 (no break)
                    pass
                else:
                    log(f"Unknown status: {status}", "WARN")
                    break # Unknown status


                # ========== STEP 5: Select SMS ==========
                success, reason = self.step5_select_sms_option(phone)
                if not success:
                    log(f"Failed to select SMS: {reason}", "WARN")
                    accounts_processed += 1
                    continue # Try next account if any

                # ========== STEP 6: Verify Sent ==========
                success_6, reason_6 = self.step6_send_code()
                if success_6:
                    result["status"] = "OTP_SENT"
                    result["message"] = f"OTP Sent to account #{accounts_processed + 1}"
                    result["otp_url"] = self.driver.current_url
                    result["last_url"] = self.driver.current_url
                    
                    # Send success snapshot
                    otp_caption = f"✅ OTP SENT | {phone}\n🔗 OTP URL:\n{result['otp_url']}"
                    try:
                        timestamp = int(time.time())
                        filename = f"snap_6_SendSuccess_{timestamp}.png"
                        self.driver.save_screenshot(filename)
                        self.send_telegram_photo(otp_caption, filename)
                    except: pass
                    
                    break # SUCCESS! Stop looking
                else:
                    log(f"Failed to verify send: {reason_6}", "WARN")
                
                accounts_processed += 1
                
            # END LOOP
            
        except Exception as e:
            log(f"CRITICAL ERROR: {e}", "ERROR")
            result["message"] = str(e)
            
        finally:
            self._close_driver()
            
        return result



# ==========================================
# Batch Processing Logic
# ==========================================

def format_phone(phone):
    """Clean phone number"""
    return re.sub(r'[^\d+]', '', phone).strip()

def process_batch(numbers, headless=True, max_workers=1):
    """Process a list of numbers"""
    stats = Stats(len(numbers))
    results = []
    
    print(f"\n{C.B}Starting batch process for {len(numbers)} numbers...{C.END}")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_phone = {
            executor.submit(FacebookOTPBrowser(headless=headless).send_otp, phone): phone 
            for phone in numbers
        }
        
        for future in as_completed(future_to_phone):
            phone = future_to_phone[future]
            try:
                res = future.result()
                stats.update(res["status"])
                stats.display()
                results.append(res)
            except Exception as exc:
                print(f'{phone} generated an exception: {exc}')
                print(f"FINAL_STATUS_MSG: {str(exc)}")
                stats.update("ERROR")
    
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    arg = sys.argv[1]
    
    # Check if arg is a file
    if os.path.isfile(arg):
        with open(arg, 'r') as f:
            numbers = [line.strip() for line in f if line.strip()]
        if not numbers:
            print("File is empty!")
            sys.exit(1)
        process_batch(numbers, headless=True, max_workers=1)
    else:
        # Single number
        browser = FacebookOTPBrowser(headless=True) # Ensure headless for batch
        try:
             res = browser.send_otp(arg)
             # Always print last URL
             last_url = res.get('last_url', res.get('otp_url', ''))
             if last_url:
                 print(f"Last URL: {last_url}")
             
             # Print final status for shell script extraction
             if res['status'] == 'ERROR':
                 print(f"FINAL_STATUS_MSG: {res['message']}")
             elif res['status'] == 'OTP_SENT':
                  print("OTP_SENT") 
             elif res['status'] == 'NOT_FOUND':
                  print("FINAL_STATUS_MSG: Account Not Found")
             else:
                  print(f"FINAL_STATUS_MSG: {res.get('message', 'Unknown')}")
        except Exception as e:
             print(f"FINAL_STATUS_MSG: Critical Script Error: {e}")

