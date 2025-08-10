from app import app, ensure_inventory_file, open_browser
import os
import threading

# Auto-open browser when running locally
if not os.environ.get('REPLIT_DEPLOYMENT'):
    threading.Timer(2.0, open_browser).start()

if __name__ == "__main__":
    ensure_inventory_file()
    app.run(host="0.0.0.0", port=5000, debug=True)