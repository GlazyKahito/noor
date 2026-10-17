"""Run the NOOR website locally (the same screens as the desktop app, in a browser).

    python web.py               http://127.0.0.1:3060
    python web.py --port 3061

The live copy is at https://noor-climate.vercel.app. The desktop app is `python app.py`.
"""
import argparse

from noor.web.server import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the NOOR website locally.")
    parser.add_argument("--port", type=int, default=3060)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    run(args.port, args.host)
