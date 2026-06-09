import json
import os
import subprocess
import sys

def main():
    print("Setting up CloakBrowser...")
    
    # 1. Install/upgrade cloakbrowser package
    try:
        import cloakbrowser
    except ImportError:
        print("Installing cloakbrowser package...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "cloakbrowser"])
        import cloakbrowser

    # 2. Ensure binary is downloaded
    print("Checking and downloading CloakBrowser binary (if not already downloaded)...")
    cloakbrowser.ensure_binary()
    info = cloakbrowser.binary_info()
    binary_path = info.get("binary_path")
    
    if not binary_path or not os.path.exists(binary_path):
        print(f"Error: CloakBrowser binary path '{binary_path}' not found.")
        sys.exit(1)
        
    print(f"CloakBrowser binary is located at: {binary_path}")

    # 3. Read config.json, update it
    config_file = "config.json"
    if not os.path.exists(config_file):
        if os.path.exists("config.example.json"):
            print("Creating config.json from config.example.json...")
            import shutil
            shutil.copy("config.example.json", config_file)
        else:
            print("Error: config.json and config.example.json not found.")
            sys.exit(1)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error reading config.json: {e}")
        sys.exit(1)

    # Set executable_path
    if "browser" not in config:
        config["browser"] = {}
    
    config["browser"]["executable_path"] = binary_path
    
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("Successfully updated config.json with CloakBrowser path!")
    except Exception as e:
        print(f"Error writing config.json: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
