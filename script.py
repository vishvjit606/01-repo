import os
import json
import pathlib
import sys
from typing import Optional

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

ASSETS_DIR = pathlib.Path("assets")
ARTIFACTS_DIR = pathlib.Path("artifacts")
ASSETS_DIR.mkdir(exist_ok=True)
ARTIFACTS_DIR.mkdir(exist_ok=True)

def get_pixabay_image_url(api_key: str, query: str = "sunset") -> Optional[str]:
    url = "https://pixabay.com/api/"
    params = {
        "key": api_key,
        "q": query,
        "image_type": "photo",
        "safesearch": "true",
        "per_page": 50,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    hits = data.get("hits") or []
    if not hits:
        return None
    # pick the first result; you can choose largeImageURL if you prefer
    return hits[0].get("webformatURL") or hits[0].get("largeImageURL")

def download(url: str, out_path: pathlib.Path) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1024 * 64):
                if chunk:
                    f.write(chunk)

def upload_to_canva(image_path: pathlib.Path) -> None:
    email = os.environ.get("CANVA_EMAIL")
    password = os.environ.get("CANVA_PASSWORD")
    if not email or not password:
        print("CANVA_EMAIL/CANVA_PASSWORD not set; skipping Canva automation.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto("https://www.canva.com/", wait_until="domcontentloaded", timeout=45000)
            # Click “Log in”
            page.get_by_role("link", name="Log in").click(timeout=30000)

            # Fill creds (selectors may need adjustment over time)
            page.fill("input[name='email']", email, timeout=30000)
            page.fill("input[name='password']", password, timeout=30000)
            page.press("input[name='password']", "Enter")

            # Wait for login to settle
            page.wait_for_load_state("networkidle", timeout=60000)

            # Navigate to Create page (optional)
            page.goto("https://www.canva.com/create/", wait_until="domcontentloaded", timeout=45000)

            # Open uploads panel (these selectors can change; adjust if needed)
            # Try generic button name first:
            try:
                page.get_by_role("button", name="Uploads").click(timeout=15000)
            except PWTimeout:
                pass  # panel might already be open

            # Set file on <input type="file"> (works even if input is hidden, as long as it's in DOM)
            page.set_input_files("input[type='file']", str(image_path))

            # Give it a moment to upload; then screenshot
            page.wait_for_timeout(5000)
            page.screenshot(path=str(ARTIFACTS_DIR / "canva_after_upload.png"), full_page=True)
            print("Upload attempted. Screenshot saved.")

        except Exception as e:
            print("Canva automation failed:", type(e).__name__, str(e))
            page.screenshot(path=str(ARTIFACTS_DIR / "error.png"), full_page=True)
        finally:
            context.close()
            browser.close()

def main():
    # 1) Download a Pixabay image
    api_key = os.environ.get("PIXABAY_API_KEY")
    query = os.environ.get("PIXABAY_QUERY", "sunset")
    if not api_key:
        print("PIXABAY_API_KEY not set. Exiting.")
        sys.exit(1)

    url = get_pixabay_image_url(api_key, query=query)
    if not url:
        print("No Pixabay hits for query:", query)
        sys.exit(1)

    img_path = ASSETS_DIR / "image.jpg"
    download(url, img_path)
    print(f"Downloaded image to: {img_path}")

    # 2) (Optional) Upload it to Canva
    upload_to_canva(img_path)

    # Always leave some artifact
    with open(ARTIFACTS_DIR / "run.json", "w") as f:
        json.dump({"pixabay_image_url": url, "query": query}, f, indent=2)
    print("Done.")

if __name__ == "__main__":
    main()
