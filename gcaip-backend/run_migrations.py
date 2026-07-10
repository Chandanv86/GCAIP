import os
import sys

# Name shadowing fix:
# The folder '/app/alembic' shadows the installed 'alembic' library.
# We modify sys.path to ensure site-packages has priority over the local directory,
# then run the migrations programmatically.
app_path = os.path.dirname(os.path.abspath(__file__))
# Remove shadowing entries
sys.path = [p for p in sys.path if p not in ("", ".", app_path)]
# Re-append app_path at the end so our app modules (db, models, etc.) can be imported by env.py
sys.path.append(app_path)

from alembic.config import Config
from alembic import command

if __name__ == "__main__":
    ini_path = os.path.join(app_path, "alembic.ini")
    print(f"Running Alembic migrations using config: {ini_path}...")
    cfg = Config(ini_path)
    command.upgrade(cfg, "head")
    print("Migrations completed successfully!")
