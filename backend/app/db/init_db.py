"""Create (or reset) the database tables.

Run from the backend/ folder:
    python -m app.db.init_db           # create any missing tables
    python -m app.db.init_db --reset   # DROP the project's tables, then recreate them
"""

import argparse

from app import models  # noqa: F401  (importing registers the tables on Base.metadata)
from app.db.base import Base
from app.db.session import engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the RegChange Radar tables.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="drop all RegChange Radar tables first (destroys all saved data)",
    )
    args = parser.parse_args()

    if args.reset:
        answer = input("This will DELETE all comparison data. Type 'yes' to continue: ")
        if answer.strip().lower() != "yes":
            print("Aborted.")
            return
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")

    Base.metadata.create_all(engine)
    print("Tables ready:", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    main()