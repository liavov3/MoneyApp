"""Password utilities shared by private login and operator-only provisioning."""
import re

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
# A synthetic hash gives unknown usernames the same password-verification work.
dummy_hash = password_hasher.hash("not-an-account-credential-84f90b81")


def normalize_username(username: str) -> str:
    value = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._@+\-]{3,80}", value):
        raise ValueError("Use 3–80 letters, numbers, or . _ @ + - for the username.")
    return value


def hash_new_password(password: str) -> str:
    if not 15 <= len(password) <= 128:
        raise ValueError("Use a password or passphrase of 15–128 characters.")
    return password_hasher.hash(password)
