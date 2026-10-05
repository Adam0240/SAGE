# Handles password hashing and verification for SAGE accounts.

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class PasswordService:
    def __init__(self):
        self.hasher = PasswordHasher()

    def hash_password(self, password: str) -> str:
        # Reject an empty password before creating its hash.
        if not password:
            raise ValueError("Password cannot be empty.")

        # Generate a salted hash to store in the users table.
        return self.hasher.hash(password)

    def verify_password(self, password_hash: str, password: str) -> bool:
        # Check the entered password against the stored hash.
        try:
            return self.hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        # Check whether a stored hash needs updated hashing settings.
        return self.hasher.check_needs_rehash(password_hash)