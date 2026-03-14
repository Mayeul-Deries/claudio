import os
import sys
import urllib.request
import urllib.error
import whisper

# The medium model URL from the whisper source code
MODEL_URL = whisper._MODELS["medium"]
# Default whisper cache directory
DOWNLOAD_ROOT = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
MODEL_FILE = os.path.join(DOWNLOAD_ROOT, "medium.pt")

def reporthook(block_num, block_size, total_size):
    downloaded = block_num * block_size
    percent = downloaded * 100 / total_size if total_size > 0 else 0
    # Create a simple progress bar
    bar_length = 40
    filled_length = int(bar_length * downloaded // total_size) if total_size > 0 else 0
    bar = '=' * filled_length + '-' * (bar_length - filled_length)
    
    sys.stdout.write(f"\rDownloading model [{bar}] {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB)")
    sys.stdout.flush()

def download_model_robustly():
    os.makedirs(DOWNLOAD_ROOT, exist_ok=True)
    
    if os.path.exists(MODEL_FILE):
        print(f"Model already exists at {MODEL_FILE}")
        return True
        
    print(f"Downloading Whisper 'medium' model (~1.5 GB)...")
    print(f"Saving to: {MODEL_FILE}")
    print("This might take a while depending on your connection.\n")
    
    # Increase timeout and add user-agent to avoid connection drops
    req = urllib.request.Request(
        MODEL_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response, open(MODEL_FILE, 'wb') as out_file:
            total_size = int(response.info().get("Content-Length", -1))
            block_size = 1024 * 8
            downloaded = 0
            
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                out_file.write(buffer)
                downloaded += len(buffer)
                
                # Progress update
                if total_size > 0:
                    percent = downloaded * 100 / total_size
                    bar_length = 40
                    filled_length = int(bar_length * downloaded // total_size)
                    bar = '=' * filled_length + '-' * (bar_length - filled_length)
                    sys.stdout.write(f"\rDownloading model [{bar}] {percent:.1f}% ({downloaded / 1024 / 1024:.1f} / {total_size / 1024 / 1024:.1f} MB)")
                else:
                    sys.stdout.write(f"\rDownloading model... {downloaded / 1024 / 1024:.1f} MB")
                sys.stdout.flush()
                
        print("\n\nDownload complete! You can now launch Claudio.")
        return True
        
    except Exception as e:
        print(f"\n\nDownload failed: {e}")
        print("Please check your internet connection and try running this script again.")
        # Clean up partial file
        if os.path.exists(MODEL_FILE):
            os.remove(MODEL_FILE)
        return False

if __name__ == "__main__":
    download_model_robustly()
