"""Exercise the browser against the real app, PostgreSQL and Redis in CI."""

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from sqlalchemy import delete

from panelprimepasar.db import SessionFactory, engine
from panelprimepasar.models import WebAdmin
from panelprimepasar.security.auth import hash_password
from panelprimepasar.security.permissions import AdminRole


async def seed(username: str, password: str) -> None:
    async with SessionFactory() as session:
        session.add(
            WebAdmin(username=username, password_hash=hash_password(password), role=AdminRole.OWNER)
        )
        await session.commit()
    await engine.dispose()


async def cleanup(username: str) -> None:
    async with SessionFactory() as session:
        await session.execute(delete(WebAdmin).where(WebAdmin.username == username))
        await session.commit()
    await engine.dispose()


def main() -> None:
    username, password = "browser-" + secrets.token_hex(6), secrets.token_urlsafe(24)
    asyncio.run(seed(username, password))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "ADMIN_JWT_SECRET": secrets.token_urlsafe(48)}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "panelprimepasar.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    artifacts = Path("browser-artifacts")
    artifacts.mkdir(exist_ok=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/health/ready", timeout=2).close()
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Application dependencies did not become ready")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1365, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                page.goto(base + "/admin/ui")
                page.get_by_label("نام کاربری", exact=True).fill(username)
                page.get_by_label("رمز عبور", exact=True).fill(password)
                page.get_by_role("button", name="ورود", exact=True).click()
                page.get_by_role("heading", name="داشبورد", exact=True).wait_for()
                page.get_by_role("button", name="پلن‌ها", exact=True).click()
                page.get_by_role("button", name="پلن جدید", exact=True).click()
                plan_name = "browser-plan-" + secrets.token_hex(6)
                dialog = page.get_by_role("dialog")
                dialog.get_by_label("نام", exact=True).fill(plan_name)
                dialog.get_by_label("حجم به بایت", exact=False).fill("1000000000000")
                dialog.get_by_label("قیمت", exact=True).fill("250000")
                dialog.get_by_role("button", name="ذخیره", exact=True).click()
                page.get_by_role("cell", name=plan_name, exact=True).wait_for()
                row = page.get_by_role("row").filter(has_text=plan_name)
                row.get_by_role("button", name="غیرفعال", exact=True).click()
                row.get_by_role("button", name="فعال", exact=True).wait_for()
                page.screenshot(path=str(artifacts / "admin-desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=str(artifacts / "admin-mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.on("dialog", lambda dialog: dialog.accept())
                row.get_by_role("button", name="حذف", exact=True).click()
                page.get_by_role("cell", name=plan_name, exact=True).wait_for(state="detached")
                page.get_by_role("button", name="خروج", exact=True).click()
                page.get_by_role("heading", name="ورود به حساب مدیر").wait_for()
                assert not page.evaluate("Object.keys(localStorage).length")
                assert not errors, errors
                print("Browser E2E passed: login, plan CRUD, activation, mobile layout, logout")
            except BaseException:
                page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        asyncio.run(cleanup(username))


if __name__ == "__main__":
    main()
