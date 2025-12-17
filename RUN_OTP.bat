@echo off
cd /d "%~dp0"
title Facebook OTP Automation
color 0A
cls

echo.
echo  ======================================================
echo       Facebook OTP Browser Automation
echo       Now with Proxy Support!
echo  ======================================================
echo.
echo  File: numbers.txt
echo  Proxies: proxies.txt
echo.
echo  [1] With Browser (visible - for testing)
echo  [2] With Browser + Proxy
echo  [3] Headless Mode (faster)
echo  [4] Headless + Proxy
echo  [5] Parallel + Proxy (FASTEST!)
echo.

set /p choice="Choose (1-5): "

if "%choice%"=="1" goto VISIBLE
if "%choice%"=="2" goto VISIBLE_PROXY
if "%choice%"=="3" goto HEADLESS
if "%choice%"=="4" goto HEADLESS_PROXY
if "%choice%"=="5" goto PARALLEL_PROXY
goto END

:VISIBLE
cls
echo.
echo  Starting with VISIBLE browser (no proxy)...
echo  Press Ctrl+C to stop
echo.
python -u fb_otp_browser.py numbers.txt
goto END

:VISIBLE_PROXY
cls
echo.
echo  Starting with VISIBLE browser + PROXY...
echo  Press Ctrl+C to stop
echo.
python -u fb_otp_browser.py numbers.txt --proxy proxies.txt
goto END

:HEADLESS
cls
echo.
echo  Starting HEADLESS mode (no proxy)...
echo  Press Ctrl+C to stop
echo.
python -u fb_otp_browser.py numbers.txt --headless
goto END

:HEADLESS_PROXY
cls
echo.
echo  Starting HEADLESS + PROXY mode...
echo  Press Ctrl+C to stop
echo.
python -u fb_otp_browser.py numbers.txt --headless --proxy proxies.txt
goto END

:PARALLEL_PROXY
cls
echo.
echo  Starting PARALLEL + HEADLESS + PROXY mode (3 workers)...
echo  This is the FASTEST mode with IP rotation!
echo  Press Ctrl+C to stop
echo.
python -u fb_otp_browser.py numbers.txt --headless --parallel --proxy proxies.txt
goto END

:END
echo.
pause
