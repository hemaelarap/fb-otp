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

# Undetected Chromedriver removed by user request
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
            
            # 3. Save Screenshot
            filename = f"fail_{step_name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            log(f"Screenshot saved to: {filename}", "INFO")
            
            # 4. Upload to Telegram
            caption = f"⚠️ FAILURE: {step_name}\nURL: {url}\nTitle: {title}"
            self.send_telegram_photo(caption, filename)
            
        except Exception as e:
            log(f"Failed to save failure snapshot: {e}", "WARN")

    def _setup_driver(self):
        """Setup Chrome WebDriver with optional proxy support"""
        log("Setting up Chrome browser...")
        
        # Mobile Viewport & User Agent (Android)
        mobile_ua = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
        
        def get_configured_options(use_mobile_emulation=True):
            """Helper to generate fresh options"""
            options = Options()
            
            if self.headless:
                options.add_argument("--headless=new")
            
            # Anti-detection options
            options.add_argument("--disable-blink-features=AutomationControlled")
            
            # UA & Window Size (Always Apply)
            options.add_argument(f"user-agent={mobile_ua}")
            options.add_argument("--window-size=375,812")
            
            if use_mobile_emulation:
                # Enable Mobile Emulation (Can cause crash on some drivers)
                mobile_emulation = {
                    "deviceMetrics": { "width": 375, "height": 812, "pixelRatio": 3.0 },
                    "userAgent": mobile_ua
                }
                options.add_experimental_option("mobileEmulation", mobile_emulation)

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
            safe_options = get_configured_options(use_mobile_emulation=True)
            
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
                        log(f"Standard Chrome (Manager) failed: {e}", "WARN")
            
            # Fallback: Direct Standard Chrome
            if not self.driver:
                try:
                    self.driver = webdriver.Chrome(options=safe_options)
                    log("Standard Chrome (direct) ready!", "OK")
                except Exception as e:
                    log(f"Standard Chrome (Direct) failed: {e}", "ERROR")

            # --- ADVANCED FINGERPRINT SPOOFING (CDP) ---
            if self.driver:
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

    def send_telegram_video(self, caption, file_path):
        """Send a video to the configured Telegram chat."""
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            log("Telegram credentials not found, skipping video send.", "WARN")
            return

        try:
            url = f"https://api.telegram.org/bot{token}/sendVideo"
            with open(file_path, "rb") as f:
                files = {"video": f}
                data = {"chat_id": chat_id, "caption": caption}
                # Increase timeout for video upload
                response = requests.post(url, files=files, data=data, timeout=60)
                
            if response.status_code == 200:
                log(f"Sent Telegram video: {caption}", "OK")
            else:
                log(f"Failed to send Telegram video: {response.text}", "WARN")
        except Exception as e:
            log(f"Error sending Telegram video: {e}", "WARN")

    def send_telegram_video(self, caption, file_path):
        """Send a video to the configured Telegram chat."""
        token = os.environ.get("TELEGRAM_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            log("Telegram credentials not found, skipping video send.", "WARN")
            return

        try:
            url = f"https://api.telegram.org/bot{token}/sendVideo"
            with open(file_path, "rb") as f:
                files = {"video": f}
                data = {"chat_id": chat_id, "caption": caption}
                # Increase timeout for video upload
                response = requests.post(url, files=files, data=data, timeout=60)
                
            if response.status_code == 200:
                log(f"Sent Telegram video: {caption}", "OK")
            else:
                log(f"Failed to send Telegram video: {response.text}", "WARN")
        except Exception as e:
            log(f"Error sending Telegram video: {e}", "WARN")

    def _take_step_snapshot(self, step_name, phone=""):
        """Helper to take and send a snapshot for a specific step"""
        try:
            if not self.driver: return
            
            # Skip if headless and no page loaded (sometimes happens)
            if self.headless and not self.driver.current_url: return

            timestamp = int(time.time())
            filename = f"snap_{step_name}_{timestamp}.png"
            self.driver.save_screenshot(filename)
            
            # Send to Telegram
            caption = f"Step: {step_name} | {phone}"
            self.send_telegram_photo(caption, filename)
            
            # Clean up local file to save space? (Optional - keeping for now for debug)
            # os.remove(filename) 
            
        except Exception as e:
            log(f"Snapshot error ({step_name}): {e}", "WARN")

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

    def step1_open_recovery_page(self):
        """Step 1: Open Facebook, handle cookies, and navigate to recovery"""
        log("Step 1: Opening Facebook Recovery Page (Mobile)...")
        try:
            self._take_step_snapshot("STEP1_START")
            self.driver.get('https://m.facebook.com/login/identify')
            self.random_sleep(2, 4)  # Reduced wait time for speed (was 8-12)
            
            # Handle Cookie Consent (European/International IPs)
            # Handle Cookie Consent (Removed by user request)
            # self._handle_cookie_consent()
            
            # Simulate human browsing behavior
            self.simulate_human_behavior()
            
            self._take_step_snapshot("STEP1_END")
            return True
        except Exception as e:
            log(f"Error opening page: {e}", "ERROR")
            self._save_failure_snapshot("step1_open_page")
            return False

    # Cookie consent handler removed by user request
    # def _handle_cookie_consent(self): ...
    
    def step2_enter_phone(self, phone):
        """Step 2: Enter phone number in search field"""
        log(f"Step 2: Entering phone number: {phone}...")
        # self._handle_cookie_consent()
        
        try:
            # Find the email/phone input field - try multiple times
            input_selectors = [
                (By.ID, "identify_email"),
                (By.NAME, "email"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "#contactpoint_step_input"),
                (By.CSS_SELECTOR, "input.inputtext._9o1w"),
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
                time.sleep(0.5)
            
            if not input_field:
                log("Could not find input field", "ERROR")
                return False
            
            # Clear and enter phone
            input_field.clear()
            input_field.send_keys(phone)
            time.sleep(0.1)
            
            log("Phone number entered!", "OK")
            self._take_step_snapshot("STEP2_END", phone)
            return True
            
        except Exception as e:
            log(f"Error entering phone: {e}", "ERROR")
            return False
    
    def step3_click_search(self):
        """Step 3: Click the search button"""
        log("Step 3: Clicking search button...")
        # self._handle_cookie_consent() 
        
        try:
            # Try different button selectors
            button_selectors = [
                (By.XPATH, "//button[contains(text(), 'Continue')]"),
                (By.XPATH, "//div[@role='button' and contains(text(), 'Continue')]"),
                (By.XPATH, "//span[contains(text(), 'Continue')]"),
                (By.XPATH, "//button[contains(@id, 'u_0_5_')]"),
                (By.NAME, "did_submit"),
                (By.CSS_SELECTOR, "button[name='did_submit']"),
                (By.ID, "did_submit"),
                (By.CSS_SELECTOR, "button._42ft._4jy0._9nq0"),
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
                        log(f"Found search/continue button: {selector}", "INFO")
                        try:
                            button.click()
                            log("Search/Continue button clicked (Standard)!", "OK")
                        except Exception as click_err:
                            log(f"Standard click failed ({click_err}), trying JS Click...", "WARN")
                            self.driver.execute_script("arguments[0].click();", button)
                            log("Search/Continue button clicked (JS)!", "OK")
                        
                            
                        time.sleep(3)
                        
                        # Optional: Capture debug screenshot after search to confirm state
                        try:
                             if not self.headless or (self.headless and not self.driver.current_url): 
                                 self.driver.save_screenshot("debug_after_search.png")
                                 self.send_telegram_photo("After Search Click", "debug_after_search.png")
                        except: pass
                        return True
                except:
                    continue
            
            # Try pressing Enter as fallback
            try:
                input_field = self.driver.find_element(By.CSS_SELECTOR, "input[name='email']")
                input_field.send_keys(Keys.ENTER)
                log("Pressed Enter to search", "OK")
                time.sleep(0.5)
                self._take_step_snapshot("STEP3_END", "")
                return True
            except:
                pass
            
            log("Could not find search button", "WARN")
            return False
            
        except Exception as e:
            log(f"Error clicking search: {e}", "ERROR")
            return False
    
    def _check_multiple_accounts(self):
        """Check if multiple accounts are displayed"""
        try:
            # Look for the list of accounts
            # Selector: tr td._9okr (Wrapper for each account)
            accounts = self.driver.find_elements(By.CSS_SELECTOR, "tr td._9okr")
            if accounts and len(accounts) > 0:
                log(f"Detected {len(accounts)} multiple accounts!", "WARN")
                return len(accounts)
            return 0
        except:
            return 0

    def step4_check_account_found(self):
        """Step 4: Check if account was found"""
        log("Step 4: Checking if account exists...")
        # self._handle_cookie_consent()
        
        # Wait for page to load properly
        time.sleep(2)
        
        try:
            page_source = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            # FIRST: Check for specific "No Search Results" error
            try:
                error_box = self.driver.find_element(By.CSS_SELECTOR, ".pam.uiBoxRed")
                error_text = error_box.text.lower()
                if "no search results" in error_text or "didn't match" in error_text:
                    log("Account NOT FOUND (Error Box)!", "WARN")
                    return "NOT_FOUND"
            except:
                pass

            # SECOND: Check URL for recovery (most reliable)
            if "recover" in current_url or "reset" in current_url:
                log("Account FOUND (URL check)!", "OK")
                self._take_step_snapshot("STEP4_FOUND_URL", "")
                return "FOUND"
            
            # THIRD: Check for Login page with "Try Another Way" button
            if "login" in current_url or "password" in page_source:
                 # Try to find and click "Try another way" button
                 try_another_selectors = [
                     (By.XPATH, "//button[contains(text(), 'Try another way')]"),
                     (By.XPATH, "//a[contains(text(), 'Try another way')]"),
                     (By.XPATH, "//div[contains(text(), 'Try another way')]"),
                     (By.XPATH, "//span[contains(text(), 'Try another way')]"),
                     (By.CSS_SELECTOR, "a[href*='/recover/initiate']"),
                     (By.CSS_SELECTOR, "a[href*='is_from_lara_screen']"),
                 ]
                 
                 for by, selector in try_another_selectors:
                     try:
                         btn = self.driver.find_element(by, selector)
                         if btn and btn.is_displayed():
                             log("Found 'Try Another Way' button - clicking...", "INFO")
                             try:
                                 btn.click()
                             except:
                                 self.driver.execute_script("arguments[0].click();", btn)
                             time.sleep(3)
                             log("Clicked 'Try Another Way' - continuing to SMS selection", "OK")
                             return "FOUND"  # Proceed to step 5 (SMS selection)
                     except:
                         continue
                 
                 # If button not found but we're on login page
                 if "try another way" in page_source:
                     log("Detected 'Try another way' text but couldn't click", "WARN")
                     return "TRY_ANOTHER_WAY"

            # FOURTH: Check for "Choose your account" page (multiple accounts)
            if "choose your account" in page_source:
                log("Detected 'Choose your account' page - clicking first account...", "INFO")
                try:
                    # Find all clickable account rows
                    account_selectors = [
                        # Specific matches for the list items shown in screenshot
                        (By.XPATH, "//div[contains(text(), 'Choose your account')]/following::div[@role='button']"), 
                        (By.XPATH, "//div[contains(text(), 'Choose your account')]/following::div[contains(@class, 'x1i10hfl')]"),
                        (By.CSS_SELECTOR, "div[role='button']"),  # Generic button
                        (By.CSS_SELECTOR, "div[data-sigil='touchable']"), # m.facebook touchable
                        (By.CSS_SELECTOR, "li"), # List items (often used in these lists)
                        (By.TAG_NAME, "li"),
                        (By.CSS_SELECTOR, "a[role='button']"),
                        (By.XPATH, "//div[contains(@class, 'x1i10hfl')]"), 
                        (By.XPATH, "//div[contains(text(), '+')]"),
                    ]
                    
                    for by, selector in account_selectors:
                        try:
                            accounts = self.driver.find_elements(by, selector)
                            if accounts and len(accounts) > 0:
                                # Click the first account (usually matches phone number)
                                accounts[0].click()
                                log(f"Clicked first account option", "OK")
                                self._take_step_snapshot("MULTI_ACC_SELECTED", "")
                                time.sleep(2)
                                return "FOUND"  # Proceed to next step
                        except:
                            continue
                except Exception as e:
                    log(f"Error clicking account: {e}", "WARN")
            
            # Fallback: Check for multiple accounts using old method
            if self._check_multiple_accounts() > 0:
                return "MULTIPLE_ACCOUNTS"

            # FIFTH: PRIORITY - Check for "not found" indicators FIRST (before FOUND)
            not_found_indicators = [
                "we couldn't find your account",
                "couldn't find your account",
                "no search results",
                "no account found",
                "we couldn't find",
                "no results",
                "create new account",
                "لم نتمكن من العثور",
                "لا توجد نتائج",
                "لم يتم العثور",
            ]
            
            for indicator in not_found_indicators:
                if indicator in page_source:
                    log(f"Account NOT FOUND (Keyword: {indicator})", "WARN")
                    return "NOT_FOUND"

            # SIXTH: Check for recovery page indicators (only after NOT_FOUND check)
            found_indicators = [
                "recover",
                "reset",
                "send code",
                "we'll send you a code",
                "reset your password",
                "حسابك",
                "إرسال الرمز",
                "إعادة تعيين",
            ]
            
            for indicator in found_indicators:
                if indicator in page_source:
                    log("Account FOUND!", "OK")
                    return "FOUND"
                    
            # Check for Profile Card (Visual element)
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, '.uiHeaderTitle') or self.driver.find_elements(By.CSS_SELECTOR, 'form[action*="recover"]'):
                     log("Account FOUND (Visual check)!", "OK")
                     return "FOUND"
            except:
                pass

            # Fallback
            log("State unsure, checking specific elements for not found...", "INFO")
            # Final specific check for the red box content if not caught earlier
            if "pam uiboxred" in page_source:
                 return "NOT_FOUND"

            log("Unknown result - assuming FOUND and continuing...", "WARN")
            return "FOUND"
            
        except Exception as e:
            log(f"Error checking account: {e}", "ERROR")
            return "ERROR"
    
    def step5_select_sms_option(self, phone=""):
        """Step 5: Select SMS recovery option (NOT email)"""
        log("Step 5: Looking for SMS option (avoiding email)...")
        # self._handle_cookie_consent()
        
        time.sleep(0.5)
        self._take_step_snapshot("STEP5_START", phone)
        
        try:
            page_source = self.driver.page_source.lower()
            
            # EARLY CHECK: Detect "Choose a way to log in" page (no SMS visible)
            if "choose a way to log in" in page_source:
                log("Detected 'Choose a way to log in' page...", "INFO")
                
                # First try to click "See more" to reveal more options
                try:
                    see_more = self.driver.find_element(By.XPATH, "//a[contains(text(), 'See more')]")
                    if see_more:
                        see_more.click()
                        log("Clicked 'See more' to reveal more options...", "INFO")
                        time.sleep(1)
                        page_source = self.driver.page_source.lower()
                except:
                    pass
                
                # Now check if SMS option is available
                if "sms" not in page_source and "text message" not in page_source:
                    log("NO SMS OPTION AVAILABLE - Only email/notification/password options", "ERROR")
                    return False, "NO_SMS_OPTION_AVAILABLE"
            
            # PRIORITY 1: Check for "We'll send you a code" page with Continue button
            # This is the direct SMS confirmation page - just click Continue
            # CRITICAL: We must NOT do this if we are on the "Choose a way" selection page
            is_selection_page = "choose a way to log in" in page_source
            
            try:
                if not is_selection_page and ("send you a code" in page_source or "we'll send" in page_source):
                    log("Detected SMS confirmation page - looking for Continue button...", "INFO")
                    continue_selectors = [
                        (By.XPATH, "//button[contains(text(), 'Continue')]"),
                        (By.XPATH, "//div[@role='button' and contains(text(), 'Continue')]"),
                        (By.XPATH, "//span[contains(text(), 'Continue')]"),
                        (By.CSS_SELECTOR, "button[type='submit']"),
                    ]
                    for by, selector in continue_selectors:
                        try:
                            btn = self.driver.find_element(by, selector)
                            if btn and btn.is_displayed():
                                btn.click()
                                log("Clicked Continue on SMS confirmation page!", "OK")
                                time.sleep(1)
                                return True, "SMS_SELECTED_DIRECTLY"
                        except:
                            continue
            except:
                pass

            # PRIORITY 2: First, check if there's a link with send_sms in href
            try:
                sms_link = self.driver.find_element(By.XPATH, "//a[contains(@href, 'send_sms')]")
                if sms_link:
                    sms_link.click()
                    log("Clicked SMS link!", "OK")
                    time.sleep(0.5)
                    self._take_step_snapshot("STEP5_SMS_LINK", phone)
                    return True, "SMS_LINK_CLICKED"
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
                            # Check if it matches our phone (last 2 digits) if possible
                            if phone and len(phone) >= 2:
                                last_digits = phone[-2:]
                                if last_digits in parent_text:
                                    log(f"Matched phone digits {last_digits} in SMS option", "OK")
                                    radio.click()
                                    time.sleep(0.3)
                                    return True, "SMS_RADIO_SELECTED_MATCHED"
                            
                            radio.click()
                            log("Selected SMS radio button (Text Match)!", "OK")
                            time.sleep(0.3)
                            return True, "SMS_RADIO_SELECTED"
                    except:
                        continue
                        
                # 3. Try Exact ID Selector (New)
                try:
                    sms_radios = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'][id*='send_sms']")
                    if sms_radios:
                        sms_radios[0].click()
                        log("Selected SMS radio button (ID Match)!", "OK")
                        return True, "SMS_ID_MATCH"
                except:
                    pass
                    
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
                        return True, "SMS_TEXT_MATCH"
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
                            return True, "PHONE_NUMBER_MATCH"
                        except:
                            continue
            except:
                pass
            
            # CHECK: If page shows "Choose a way to log in" but no SMS found
            page_source = self.driver.page_source.lower()
            no_sms_indicators = [
                "choose a way to log in",
                "get code via facebook notification",
                "get code or link via email",
                "enter password to log in",
            ]
            
            has_login_options = any(ind in page_source for ind in no_sms_indicators)
            
            if has_login_options:
                # Check if SMS is available
                sms_available = "sms" in page_source or "text message" in page_source
                if not sms_available:
                    log("NO SMS OPTION AVAILABLE - Only email/notification/password options found", "ERROR")
                    return False, "NO_SMS_OPTION_VISIBLE"
            
            log("Could not find specific SMS option - may need manual selection", "WARN")
            return False, "SMS_OPTION_NOT_FOUND"
            
        except Exception as e:
            log(f"Error searching number: {e}", "ERROR")
            self._save_failure_snapshot("step5_error")
            return False, f"STEP5_ERROR: {str(e)}"
    
    def step6_send_code(self):
        """Step 6: Click send code / continue button"""
        log("Step 6: Clicking 'Continue' / 'Send Code'...")
        self._take_step_snapshot("STEP6_START")
        
        try:
            # PRIORITY: Try Continue button first with JS fallback
            continue_selectors = [
                (By.XPATH, "//button[contains(text(), 'Continue')]"),
                (By.XPATH, "//div[@role='button' and contains(text(), 'Continue')]"),
                (By.XPATH, "//span[contains(text(), 'Continue')]"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Send')]"),
                (By.XPATH, "//button[contains(text(), 'متابعة')]"),
                (By.XPATH, "//button[contains(text(), 'إرسال')]"),
                (By.CSS_SELECTOR, "[data-testid='recover_nonce_next_button']"),
                (By.CSS_SELECTOR, "[role='button']"),
            ]
            
            clicked = False
            for by, selector in continue_selectors:
                try:
                    buttons = self.driver.find_elements(by, selector)
                    for button in buttons:
                        try:
                            if button.is_displayed() and button.is_enabled():
                                # Try standard click first
                                try:
                                    button.click()
                                    log(f"Clicked button (Standard): {selector}", "OK")
                                    clicked = True
                                except Exception as click_err:
                                    # Fallback to JS click
                                    self.driver.execute_script("arguments[0].click();", button)
                                    log(f"Clicked button (JS): {selector}", "OK")
                                    clicked = True
                                
                                if clicked:
                                    time.sleep(2)  # Wait for page to respond
                                    break
                        except:
                            continue
                    if clicked:
                        break
                except:
                    continue
            
            if not clicked:
                log("Could not click any button!", "WARN")
                return False, "BUTTON_CLICK_FAILED"
            
            # Wait and verify code was sent
            # INCREASED WAIT: Mobile pages load slowly
            time.sleep(5)
            page_source = self.driver.page_source.lower()
            current_url = self.driver.current_url.lower()
            
            # FAIL CHECK: Did we send an email instead of SMS?
            if "sent a code to your email" in page_source or "via email" in page_source:
                log("FAILED: Code sent to EMAIL, not SMS!", "ERROR")
                return False, "FAILED_EMAIL_SENT"

            # FAIL CHECK: Captcha / Security Check
            if "enter these letters" in page_source or "security check" in page_source or "play audio" in page_source or "recaptcha" in page_source:
                log("FAILED: Captcha/Security Check detected!", "ERROR")
                return False, "FAILED_CAPTCHA_REQUIRED"

            success_indicators = [
                "enter code",
                "we sent",
                "code sent",
                "check your phone",
                "enter the code",
                "أدخل الرمز",
                "تم الإرسال",
            ]
            
            for indicator in success_indicators:
                if indicator in page_source:
                    log("*** OTP CODE SENT SUCCESSFULLY! ***", "SUCCESS")
                    return True, "OTP_SENT_SUCCESS"
            
            if "code" in current_url:
                log("*** OTP CODE SENT! ***", "SUCCESS")
                return True, "OTP_SENT_URL_MATCH"
            
            # If we clicked but can't confirm, still return True but warn
            log("Button clicked - Code may have been sent - check phone!", "OK")
            return True, "OTP_POSSIBLY_SENT"
            
        except Exception as e:
            log(f"Error sending code: {e}", "ERROR")
            return False, f"STEP6_ERROR: {str(e)}"
    
    def send_otp(self, phone):
        """Main function: Send OTP to phone - 3-STEP FLOW"""
        original_phone = phone
        phone = format_phone(phone)
        
        print(f"\n{'='*60}")
        print(f"{C.BOLD}{C.CYAN}   Facebook OTP - {phone}{C.END}")
        print("="*60)
        
        result = {"phone": phone, "status": "ERROR", "message": "Unknown error", "last_url": ""}
        
        try:
            # Setup browser
            if not self._setup_driver():
                result["message"] = "Failed to setup browser"
                return result
            

            
            # LOOP for Multiple Accounts (Default 1 pass)
            max_accounts_to_process = 5
            accounts_processed = 0
            
            # Only loop if we detect multiple accounts, but we need an outer loop to handle the retry logic
            while accounts_processed < max_accounts_to_process:
                
                # If this is the 2nd+ iteration, we need to restart the flow to get a clean state
                if accounts_processed > 0:
                    log(f"--- Processing Account #{accounts_processed + 1} ---", "INFO")
                    time.sleep(2)
                
                # ========== STEP 1: Open identify page and search ==========
                if not self.step1_open_recovery_page():
                    result["message"] = "Failed to open recovery page"
                    self._take_step_snapshot("1_OpenFail", phone)
                    break # Critical failure
                self._take_step_snapshot("1_Opened", phone)
                
                # Enter phone
                self._take_step_snapshot("2_BeforePhone", phone)
                if not self.step2_enter_phone(phone):
                    result["message"] = "Failed to enter phone"
                    self._take_step_snapshot("2_PhoneFail", phone)
                    break
                self._take_step_snapshot("2_AfterPhone", phone)
                
                # Search
                self._take_step_snapshot("3_BeforeSearch", phone)
                if not self.step3_click_search():
                    result["message"] = "Failed to click search"
                    self._take_step_snapshot("3_SearchFail", phone)
                    break
                # self._take_step_snapshot("3_AfterSearch", phone) # step3 has its own snapshot now
                    
                # Check Result
                self._take_step_snapshot("4_BeforeChekResult", phone)
                status = self.step4_check_account_found()
                
                # Check 2: Try a quick snapshot of the result immediately
                self._take_step_snapshot(f"4_ResultState_{status}", phone)
                
                if status == "NOT_FOUND":
                    log("Account NOT FOUND (Final)", "WARN")
                    result["status"] = "NOT_FOUND"
                    result["message"] = "Number not linked to any Facebook account"
                    # Capture debug
                    self._save_failure_snapshot("not_found_final")
                    break
                
                elif status == "TRY_ANOTHER_WAY":
                    log("Redirected to Login - Clicking 'Try Another Way'...", "INFO")
                    try:
                        # Click the button
                        btn = self.driver.find_element(By.CSS_SELECTOR, "a[href*='/recover/initiate/?is_from_lara_screen=1']")
                        btn.click()
                        time.sleep(5)
                        # Verify we are now on recovery page
                        if "recover" in self.driver.current_url or "reset" in self.driver.current_url:
                             status = "FOUND" # Proceed to next steps
                        else:
                             log("Failed to navigate to recovery after clicking button", "ERROR")
                             break
                    except Exception as e:
                        log(f"Error processing Try Another Way: {e}", "ERROR")
                        break

                if status == "MULTIPLE_ACCOUNTS":
                    log("Multiple accounts detected!", "INFO")
                    # Find all "This is me" buttons
                    try:
                        buttons = self.driver.find_elements(By.CSS_SELECTOR, "a[role='button']")
                        # Filter for "This is me" buttons if possible, or just take non-cancel ones
                        # The text usually "This is my account"
                        valid_buttons = []
                        for b in buttons:
                             if "account" in b.text.lower() or "هذا إيميل" in b.text or "حسابي" in b.text:
                                 valid_buttons.append(b)
                        
                        num_accounts = len(valid_buttons)
                        log(f"Found {num_accounts} valid account buttons.", "INFO")
                        
                        if accounts_processed >= num_accounts:
                            log("All accounts processed.", "OK")
                            break
                            
                        # Click the button for the current index
                        try:
                            target_btn = valid_buttons[accounts_processed]
                            log(f"Selecting account #{accounts_processed + 1}...", "INFO")
                            target_btn.click()
                            time.sleep(5)
                            # Now we continue to Step 5...
                        except Exception as e:
                            log(f"Error identifying account button: {e}", "ERROR")
                            break
                            
                    except Exception as e:
                        log(f"Error handling multiple accounts: {e}", "ERROR")
                        break
                elif status == "FOUND":
                    if accounts_processed > 0:
                        # We are looping but status is just FOUND?
                        # This implies we might have lost the multi-account state or it was a single account
                         break # Stop looping if we only found one
                else:
                    break


                # ========== STEP 5 & 6: Recover ==========
                # Step 5: Select SMS
                self._take_step_snapshot("5_BeforeSMS", phone)
                success, reason = self.step5_select_sms_option(phone)
                if success:
                    self._take_step_snapshot("5_AfterSMS", phone)
                    
                    # Step 6: Send Code
                    self._take_step_snapshot("6_BeforeSend", phone)
                    # Step 6: Send Code
                    self._take_step_snapshot("6_BeforeSend", phone)
                    success_6, reason_6 = self.step6_send_code()
                    if success_6:
                        result["status"] = "OTP_SENT"
                        result["message"] = f"OTP Sent to account #{accounts_processed + 1}"
                        result["otp_url"] = self.driver.current_url  # Capture final URL for OTP entry
                        result["last_url"] = self.driver.current_url
                        
                        # Send success snapshot with OTP URL in caption
                        otp_caption = f"✅ OTP SENT | {phone}\n🔗 OTP URL:\n{result['otp_url']}"
                        try:
                            timestamp = int(time.time())
                            filename = f"snap_6_SendSuccess_{timestamp}.png"
                            self.driver.save_screenshot(filename)
                            self.send_telegram_photo(otp_caption, filename)
                        except Exception as e:
                            log(f"Snapshot error: {e}", "WARN")
                        
                        log(f"OTP Sent for Account {accounts_processed + 1} ({reason_6})", "SUCCESS")
                        log(f"OTP URL: {result['otp_url']}", "INFO")
                    else:
                        result["message"] = reason_6
                        # Sanitize reason for filename
                        safe_reason_6 = "".join(c for c in reason_6 if c.isalnum() or c in ('_', '-'))[:25]
                        self._take_step_snapshot(f"FAILED_{safe_reason_6}", phone)
                        log(f"Failed to send code: {reason_6}", "ERROR")
                else:
                    result["message"] = reason
                    # Use the specific failure reason for the snapshot name to show in Telegram
                    # 'reason' will be like NO_SMS_OPTION_VISIBLE or SMS_OPTION_NOT_FOUND
                    # We sanitize it for filename
                    safe_reason = "".join(c for c in reason if c.isalnum() or c in ('_', '-'))[:25]
                    self._take_step_snapshot(f"FAILED_{safe_reason}", phone)
                    log(f"Could not find SMS option for Account {accounts_processed + 1} ({reason})", "WARN")

                accounts_processed += 1
                
                # Check if we should loop again (only if valid multiple accounts were found prev)
                # If we were in single account mode, break
                if status == "FOUND" or status == "TRY_ANOTHER_WAY":
                    break
            
            # Final result check
            if result["status"] == "OTP_SENT":
                 return result
            elif result["status"] == "NOT_FOUND":
                 return result
            else:
                 result["status"] = "FAILED"
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
            # STOP RECORDING AND SEND VIDEO
            try:
                if 'recorder' in locals() and recorder and VIDEO_AVAILABLE:
                    recorder.stop()
                    log("Stopped video recording.", "INFO")
                    
                    if os.path.exists(video_file):
                        caption = f"Process Video | {phone} | Status: {result['status']}"
                        self.send_telegram_video(caption, video_file)
                    else:
                        log("Video file not generated (using fallback stats).", "WARN")
                
                # Fallback: If no video, try sending a photo dump if one exists
                # (You may want to re-implement screenshot logic here if video is critical, 
                # but currently we rely on video. If it fails, we assume no visual sent)
                if not VIDEO_AVAILABLE:
                     log("Video skipped (OpenCV missing). Sending final screenshot.", "INFO")
                     if self.driver:
                         self.driver.save_screenshot("debug_final_fallback.png")
                         self.send_telegram_photo(f"Final State ({phone})", "debug_final_fallback.png")

            except Exception as e:
                log(f"Error handling video/media: {e}", "WARN")

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
        print(f"FINAL_STATUS_MSG: {result.get('message', 'Unknown Error')}")


if __name__ == '__main__':
    main()
