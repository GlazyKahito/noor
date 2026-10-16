"""Start NOOR locally:  python run.py            (http://127.0.0.1:3060)
                        python run.py --port 3061
                        python run.py --reset    (delete the local database and rebuild the demo data)
"""
import argparse
import os

from noor import settings
from noor.web.server import run


def main():
    """Read command-line options and start the server."""
    parser = argparse.ArgumentParser(description="Run the NOOR web app locally.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("NOOR_PORT", 3060)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--reset", action="store_true", help="delete the local database first")
    args = parser.parse_args()
    if args.reset and os.path.exists(settings.database_path()):
        os.remove(settings.database_path())
        print("Deleted", settings.database_path())
    run(args.port, args.host)


if __name__ == "__main__":
    main()
