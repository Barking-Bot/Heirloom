#!/usr/bin/env python3
"""Heirloom - a family tree keeper that runs on your own computer.

    python3 start_heirloom.py                 # opens in your browser
    python3 start_heirloom.py --data "D:/Smith Family"
    python3 start_heirloom.py --port 9000 --no-browser
"""

import argparse
import os
import sys
import threading
import webbrowser

if sys.version_info < (3, 8):
    sys.exit("Heirloom needs Python 3.8 or newer: https://www.python.org/downloads/")

from heirloom.server import serve

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description="Heirloom family tree")
    ap.add_argument("--data", default=os.path.join(HERE, "family-data"),
                    help="folder holding your family's database and photos "
                         "(default: family-data next to this program)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = ap.parse_args()

    httpd, store = serve(args.data, args.port)
    url = f"http://localhost:{httpd.server_address[1]}/"
    print(f"Heirloom is running at {url}")
    print(f"Your family's data is kept in: {store.data_dir}")
    print("Leave this window open while you work. Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your data is saved.")
    finally:
        httpd.server_close()
        store.conn.close()


if __name__ == "__main__":
    main()
