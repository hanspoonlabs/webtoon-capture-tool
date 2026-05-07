import streamlit as st
from playwright.sync_api import sync_playwright
from pathlib import Path
import zipfile
import re
import shutil
import time
from PIL import Image

st.set_page_config(page_title="Webtoon Screenshot Tool", layout="centered")
st.title("Webtoon Screenshot Tool")

uploaded_file = st.file_uploader("Upload URL txt file", type=["txt"])
project_name = st.text_input("Project name", value="webtoon_project")
shots = st.number_input("Screenshots per chapter", min_value=1, max_value=200, value=95)

merge_enabled = st.checkbox("Merge screenshots by chapter", value=True)

merge_output = st.selectbox(
    "Merge output format",
    ["PDF", "Long JPG"],
    index=0
)

start = st.button("Start Capture")

def safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or f"project_{int(time.time())}"

def chapter_name(url, idx):
    m = re.search(r"chapter-(\d+)", url)
    no = m.group(1) if m else str(idx)
    return f"chapter_{int(no):03d}"

def close_popup(page):
    selectors = [
        "button:has-text('View Page')",
        "button:has-text('Continue')",
        "button:has-text('Close')",
        "text=View Page",
        "text=Continue",
        "[aria-label='Close']",
        ".close",
    ]
    for sel in selectors:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click(timeout=1500, force=True)
                page.wait_for_timeout(800)
                return
        except:
            pass

def make_chapter_pdf(folder):
    files = sorted(folder.glob("*.jpg"))
    if not files:
        return

    images = [Image.open(f).convert("RGB") for f in files]
    pdf_path = folder.parent / f"{folder.name}.pdf"

    images[0].save(pdf_path, save_all=True, append_images=images[1:])

    for img in images:
        img.close()

def make_chapter_long_jpg(folder):
    files = sorted(folder.glob("*.jpg"))
    if not files:
        return

    images = [Image.open(f).convert("RGB") for f in files]

    width = max(img.width for img in images)
    height = sum(img.height for img in images)

    merged = Image.new("RGB", (width, height), "white")

    y = 0
    for img in images:
        merged.paste(img, (0, y))
        y += img.height

    merged.save(folder.parent / f"{folder.name}_merged.jpg", "JPEG", quality=85)

    for img in images:
        img.close()

def capture(urls, output_dir, shots, status_box, progress_bar, merge_enabled, merge_output):
    total_steps = len(urls) * shots
    done = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for idx, url in enumerate(urls, start=1):
            folder = output_dir / chapter_name(url, idx)
            folder.mkdir(parents=True, exist_ok=True)

            status_box.info(f"Starting {folder.name}")

            page = browser.new_page(viewport={"width": 900, "height": 1300})
            page.goto(url)
            page.wait_for_timeout(2500)

            close_popup(page)

            page.evaluate("window.scrollTo(0,0)")
            page.wait_for_timeout(1000)

            for i in range(1, shots + 1):
                path = folder / f"{i:03d}.jpg"
                page.screenshot(path=str(path), type="jpeg", quality=80)

                done += 1
                progress_bar.progress(done / total_steps)

                status_box.info(f"{folder.name} | {i}/{shots}")

                # 🔥 핵심: 겹침 최소화
                page.mouse.wheel(0, 1250)
                page.wait_for_timeout(400)

            page.close()

            if merge_enabled:
                status_box.info(f"Merging {folder.name}")

                if merge_output == "PDF":
                    make_chapter_pdf(folder)
                else:
                    make_chapter_long_jpg(folder)

        browser.close()

def zip_folder(folder):
    zip_path = folder.with_suffix(".zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(folder.parent))

    return zip_path

if start:
    if not uploaded_file:
        st.error("Upload txt first")
    else:
        urls = uploaded_file.read().decode("utf-8").splitlines()
        urls = [u.strip() for u in urls if u.strip()]

        project = safe_name(project_name)
        output_dir = Path("outputs") / project

        if output_dir.exists():
            shutil.rmtree(output_dir)

        output_dir.mkdir(parents=True)

        progress_bar = st.progress(0)
        status_box = st.empty()

        capture(
            urls,
            output_dir,
            int(shots),
            status_box,
            progress_bar,
            merge_enabled,
            merge_output
        )

        zip_path = zip_folder(output_dir)

        st.success("Done!")

        with open(zip_path, "rb") as f:
            st.download_button("Download ZIP", f, file_name=zip_path.name)
