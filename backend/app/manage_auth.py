"""Operator-only account provisioning. Never expose this through the API.

Run `python -m app.manage_auth` locally; passwords are entered without echo.
Run with --reset to replace an existing account and revoke all its sessions.
"""
import argparse
import asyncio
import getpass

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.models import PrivateAccount, PrivateLoginWindow, PrivateSession, User
from app.private_passwords import hash_new_password, normalize_username


async def provision_owner(username: str, password: str, *, reset: bool = False) -> None:
    username = normalize_username(username)
    encoded = hash_new_password(password)
    user_id = get_settings().owner_user_id
    async with get_sessionmaker()() as db:
        async with db.begin():
            user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise ValueError("The configured owner is missing. Apply migrations and check OWNER_USER_ID.")
            account = await db.scalar(select(PrivateAccount).where(
                PrivateAccount.user_id == user_id,
            ).with_for_update())
            if account is not None and not reset:
                raise ValueError("An owner login already exists. Use --reset only to replace it.")
            if account is None:
                db.add(PrivateAccount(user_id=user_id, username=username, password_hash=encoded))
            else:
                from datetime import datetime, timezone
                account.username = username
                account.password_hash = encoded
                account.updated_at = datetime.now(timezone.utc)
            await db.execute(delete(PrivateSession).where(PrivateSession.user_id == user_id))
            await db.execute(delete(PrivateLoginWindow).where(PrivateLoginWindow.user_id == user_id))


def main():
    parser = argparse.ArgumentParser(description="Set up MoneySaver's private owner login.")
    parser.add_argument("--reset", action="store_true", help="Replace the password and revoke every session.")
    args = parser.parse_args()
    username = input("Username: ")
    password = getpass.getpass("Password / passphrase (15+ characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords did not match. No changes made.")

    async def run():
        try:
            await provision_owner(username, password, reset=args.reset)
        finally:
            await dispose_engine()
    try:
        asyncio.run(run())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit("Setup failed. Check database connectivity and migrations; no credentials were printed.") from None
    print("Private login saved. Existing financial data was preserved.")


if __name__ == "__main__":
    main()
