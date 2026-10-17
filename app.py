"""Start NOOR — Climate Intelligence (Tkinter desktop application).

    python app.py            open the application window
    python app.py --reset    delete the local database, rebuild the demo data, then open the window
    python app.py --init     create the database (and the demo data on a first run) and exit, no window

The database file is instance/noor.db inside this folder (set NOOR_DB_PATH to use another file).
"""
import argparse
import os
import sys

from noor import settings


def init_database():
    """Create the tables and, on a fresh database, load the demo data. Safe to run again."""
    from noor.database import Database
    from noor.service import NoorService

    db = Database()
    try:
        summary = NoorService(db).setup()
        counts = db.table_counts()
    finally:
        db.close()
    print("Database:", settings.database_path())
    print("Loaded the synthetic demonstration data." if summary else "Database already initialised; nothing added.")
    for table, rows in counts.items():
        print(f"  {table:<17} {rows:>6} rows")


def main():
    """Read the command-line options, then start the window."""
    parser = argparse.ArgumentParser(description="NOOR — Climate Intelligence desktop application")
    parser.add_argument("--reset", action="store_true", help="delete the local database first")
    parser.add_argument("--init", action="store_true", help="prepare the database and exit without a window")
    args = parser.parse_args()

    path = settings.database_path()
    if args.reset and os.path.exists(path):
        os.remove(path)
        print("Deleted", path)
    if args.init:
        init_database()
        return 0

    try:
        from noor.gui.main_window import NoorApp
        app = NoorApp()
    except ImportError as exc:
        print("A required package is missing:", exc, "\nInstall them with:  python -m pip install -r requirements.txt")
        return 1
    except Exception as exc:  # noqa: BLE001 - e.g. Tk cannot open a display
        print("NOOR could not open its window:", exc)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
