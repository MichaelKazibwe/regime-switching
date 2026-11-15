"""Local console-only pilot invitations, revocation and SQLite backups."""

import argparse
import getpass
import json
from pathlib import Path

from pilot_auth import AuthStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("var/pilot/auth.sqlite3"))
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("add-user")
    add.add_argument("username")
    add.add_argument("--role", choices=["viewer", "tester"], default="tester")
    revoke = sub.add_parser("revoke-user")
    revoke.add_argument("username")
    reset = sub.add_parser("reset-password")
    reset.add_argument("username")
    reset.add_argument("--reactivate", action="store_true")
    sub.add_parser("list-users")
    backup = sub.add_parser("backup")
    backup.add_argument("destination", type=Path)
    args = parser.parse_args()
    auth = AuthStore(args.database)
    if args.action in {"add-user", "reset-password"}:
        password = getpass.getpass("Temporary password (12–256 characters): ")
        if password != getpass.getpass("Repeat temporary password: "):
            raise ValueError("Passwords do not match")
        if args.action == "add-user":
            auth.add_user(args.username, password, role=args.role)
        else:
            auth.reset_password(args.username, password, reactivate=args.reactivate)
        print("Temporary password saved. Password change is required at next login.")
    elif args.action == "revoke-user":
        auth.revoke_user(args.username)
        print("Account disabled and sessions revoked.")
    elif args.action == "backup":
        auth.backup(args.destination)
        print("Private backup verified.")
    else:
        print(json.dumps(auth.list_users(), indent=2))


if __name__ == "__main__":
    main()
