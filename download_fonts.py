import os
import urllib.request

FONTS_DIR = os.path.join("static", "fonts")

# URLs to raw TTF files on GitHub or Google Fonts (Using a reliable mirror for direct TTF downloads)
FONTS = {
    "NotoSans-Regular.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
    "NotoSansBengali-Regular.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansBengali/NotoSansBengali-Regular.ttf",
    "NotoSansDevanagari-Regular.ttf": "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf"
}

def main():
    if not os.path.exists(FONTS_DIR):
        os.makedirs(FONTS_DIR)
        print(f"Created directory: {FONTS_DIR}")

    for filename, url in FONTS.items():
        filepath = os.path.join(FONTS_DIR, filename)
        if not os.path.exists(filepath):
            print(f"Downloading {filename}...")
            try:
                urllib.request.urlretrieve(url, filepath)
                print(f"Successfully downloaded {filename}")
            except Exception as e:
                print(f"Failed to download {filename}: {e}")
        else:
            print(f"{filename} already exists, skipping.")

if __name__ == "__main__":
    main()
