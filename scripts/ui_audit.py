"""Audit UI live https://proxyai.live dengan Playwright (headless Chromium).

Alur nyata: landing -> register -> login -> dashboard -> profile -> pricing,
sambil merekam screenshot, error console, dan request gagal.
"""
import json
import os
import time
from playwright.sync_api import sync_playwright

BASE = "https://proxyai.live"
OUT = os.path.join(os.environ.get("TEMP", "."), "ui_audit")
os.makedirs(OUT, exist_ok=True)
EMAIL = f"uitest-{int(time.time())}@example.com"
PW = "TestPass123!"
report = {"email": EMAIL, "pages": {}, "console": [], "network_fail": []}


def attach(page):
    page.on(
        "console",
        lambda m: report["console"].append({"url": page.url, "type": m.type, "text": m.text[:300]})
        if m.type in ("error", "warning")
        else None,
    )
    page.on("pageerror", lambda e: report["console"].append({"url": page.url, "type": "pageerror", "text": str(e)[:300]}))
    page.on(
        "response",
        lambda r: report["network_fail"].append({"url": r.url[:180], "status": r.status, "page": page.url})
        if r.status >= 400 and "favicon" not in r.url
        else None,
    )


def shot(page, name, full=False):
    try:
        page.screenshot(path=os.path.join(OUT, name), full_page=full, timeout=20000)
    except Exception:
        pass


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 950})
    page = ctx.new_page()
    attach(page)

    # ---------- 1. LANDING ----------
    try:
        r = page.goto(BASE, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)
        info = {"status": r.status if r else None, "title": page.title()}
        info["h1"] = page.evaluate("() => document.querySelector('h1')?.innerText || null")
        info["videos"] = page.evaluate(
            """() => [...document.querySelectorAll('video')].map(v => ({
                 src: (v.currentSrc || v.src).split('/').pop(),
                 videoW: v.videoWidth, videoH: v.videoHeight,
                 boxW: v.clientWidth, boxH: v.clientHeight,
                 boxRatio: +(v.clientWidth / Math.max(v.clientHeight,1)).toFixed(2),
                 t: +v.currentTime.toFixed(1), paused: v.paused, muted: v.muted }))"""
        )
        page.wait_for_timeout(1500)
        info["video_time_after_1s5"] = page.evaluate(
            "() => [...document.querySelectorAll('video')].map(v => +v.currentTime.toFixed(1))"
        )
        info["anchors"] = page.evaluate(
            "() => ['home','features','how','demo'].map(id => [id, !!document.getElementById(id)])"
        )
        info["cta_links"] = page.evaluate(
            "() => [...document.querySelectorAll('a')].map(a => a.getAttribute('href')).filter(Boolean)"
        )
        shot(page, "01_landing.png", full=True)
        try:
            page.click("a[href='#features']")
            page.wait_for_timeout(900)
            info["anchor_scroll_y"] = page.evaluate("() => Math.round(window.scrollY)")
        except Exception as exc:
            info["anchor_click_error"] = str(exc)[:200]
        report["pages"]["/"] = info
    except Exception as exc:
        report["pages"]["/"] = {"error": str(exc)[:300]}


    # ---------- 2. REGISTER ----------
    try:
        page.goto(f"{BASE}/register", wait_until="networkidle", timeout=60000)
        info = {
            "inputs": page.evaluate(
                "() => [...document.querySelectorAll('input')].map(i => ({type:i.type,name:i.name||i.id,ph:i.placeholder}))"
            ),
            "buttons": page.evaluate(
                "() => [...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean)"
            ),
        }
        shot(page, "02_register.png")
        page.locator("input[type='email'], input[name='email']").first.fill(EMAIL)
        pws = page.locator("input[type='password']")
        for i in range(pws.count()):
            pws.nth(i).fill(PW)
        name_input = page.locator("input[name='name'], input[placeholder*='name' i], input[placeholder*='nama' i]")
        if name_input.count():
            name_input.first.fill("UI Test")
        page.locator("button[type='submit'], button:has-text('Create'), button:has-text('Sign up')").first.click()
        page.wait_for_timeout(6000)
        info["after_url"] = page.url
        info["after_text"] = page.evaluate("() => document.body.innerText.slice(0, 500)")
        shot(page, "03_register_result.png")
        report["pages"]["/register"] = info
    except Exception as exc:
        report["pages"]["/register"] = {"error": str(exc)[:300]}
        shot(page, "03_register_error.png")

    # ---------- 3. LOGIN ----------
    try:
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
        info = {
            "buttons": page.evaluate(
                "() => [...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean)"
            )
        }
        page.locator("input[type='email'], input[name='email']").first.fill(EMAIL)
        page.locator("input[type='password']").first.fill(PW)
        page.locator("button[type='submit'], button:has-text('Sign in'), button:has-text('Login')").first.click()
        page.wait_for_timeout(6000)
        info["after_url"] = page.url
        info["after_text"] = page.evaluate("() => document.body.innerText.slice(0, 400)")
        info["token"] = page.evaluate("() => (localStorage.getItem('token')||'').slice(0,12)")
        shot(page, "04_login_result.png")
        report["pages"]["/login"] = info
    except Exception as exc:
        report["pages"]["/login"] = {"error": str(exc)[:300]}

    # ---------- 4. DASHBOARD + klik Connect YouTube ----------
    try:
        page.goto(f"{BASE}/dashboard", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3500)
        info = {"url": page.url}
        info["text"] = page.evaluate("() => document.body.innerText.slice(0, 900)")
        info["buttons"] = page.evaluate(
            "() => [...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean)"
        )
        shot(page, "05_dashboard.png", full=True)
        yt = page.locator("button:has-text('YouTube')").first
        if yt.count():
            yt.click()
            page.wait_for_timeout(5000)
            info["youtube_click_url"] = page.url
            info["youtube_click_text"] = page.evaluate("() => document.body.innerText.slice(0, 700)")
            shot(page, "06_youtube_click.png")
        report["pages"]["/dashboard"] = info
    except Exception as exc:
        report["pages"]["/dashboard"] = {"error": str(exc)[:300]}
        shot(page, "05_dashboard_error.png")

    # ---------- 5. PROFILE ----------
    try:
        page.goto(f"{BASE}/profile", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3500)
        info = {"url": page.url}
        info["text"] = page.evaluate("() => document.body.innerText.slice(0, 1200)")
        info["buttons"] = page.evaluate(
            "() => [...document.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean)"
        )
        shot(page, "07_profile.png", full=True)
        report["pages"]["/profile"] = info
    except Exception as exc:
        report["pages"]["/profile"] = {"error": str(exc)[:300]}
        shot(page, "07_profile_error.png")

    # ---------- 6. PRICING ----------
    try:
        r = page.goto(f"{BASE}/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1200)
        shot(page, "08_pricing.png", full=True)
        report["pages"]["/pricing"] = {
            "status": r.status if r else None,
            "actions": page.evaluate(
                "() => [...document.querySelectorAll('button, a')].map(b => b.innerText.trim()).filter(t => t && t.length < 40)"
            )[:25],
        }
    except Exception as exc:
        report["pages"]["/pricing"] = {"error": str(exc)[:300]}

    # ---------- 7. MOBILE ----------
    try:
        mctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        mp = mctx.new_page()
        mp.goto(BASE, wait_until="networkidle", timeout=60000)
        mp.wait_for_timeout(1500)
        shot(mp, "09_mobile.png", full=True)
    except Exception:
        pass

    browser.close()

with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=1, ensure_ascii=False)

print("OUT:", OUT)
print(json.dumps(report, indent=1, ensure_ascii=False)[:12000])
