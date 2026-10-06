# Applies SAGE's account rules before a user is added to the database.

from database.models import User
from database.user_repository import UserRepository
from services.password_service import PasswordService


VALID_ROLES = {"boss_admin", "steam_specialist", "base_specialist"}


class AccountService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_service: PasswordService,
    ):
        # Receive these objects so account rules can be tested without
        # connecting to PostgreSQL.
        self.user_repository = user_repository
        self.password_service = password_service

    def list_accounts(self, actor_id: int) -> list[User]:
        actor = self.user_repository.get_by_id(actor_id)
        if actor is None or not actor.is_active:
            raise PermissionError("An active staff account is required.")
        if actor.role not in ("boss_admin", "steam_specialist"):
            raise PermissionError("You cannot list other accounts.")

        accounts = self.user_repository.get_all()
        if actor.role == "steam_specialist":
            return [
                user for user in accounts
                if user.id == actor.id or user.role == "base_specialist"
            ]
        return accounts

    def create_account(
        self,
        actor_id: int,
        name: str,
        username: str,
        password: str,
        role: str,
    ) -> User:
        # Look up the person making the change. The displayed mode in the
        # interface is not used to decide what this person may do.
        actor = self.user_repository.get_by_id(actor_id)

        if actor is None or not actor.is_active:
            raise PermissionError("An active staff account is required.")

        if role not in VALID_ROLES:
            raise ValueError("Unknown account role.")

        # A Boss Admin can assign any role. A STEAM Specialist can create
        # Work Study Assistants only. Work Study Assistants cannot create users.
        if actor.role == "boss_admin":
            allowed_roles = VALID_ROLES
        elif actor.role == "steam_specialist":
            allowed_roles = {"base_specialist"}
        else:
            allowed_roles = set()

        if role not in allowed_roles:
            raise PermissionError("You cannot create this type of account.")

        # Match the limits in the User model and store usernames consistently.
        name = name.strip()
        username = username.strip().lower()

        if not name or len(name) > 100:
            raise ValueError("Name must contain between 1 and 100 characters.")

        if (
            not username
            or len(username) > 50
            or any(character.isspace() for character in username)
        ):
            raise ValueError(
                "Username must contain between 1 and 50 characters "
                "and cannot contain spaces."
            )

        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters.")

        # Store a password hash, never the password entered in the interface.
        user = User(
            name=name,
            username=username,
            password_hash=self.password_service.hash_password(password),
            role=role,
            is_active=True,
        )

        # The repository writes through its session. The caller will commit
        # the transaction when the complete account operation succeeds.
        return self.user_repository.add(user)

    def update_account(
        self,
        actor_id: int,
        target_id: int,
        *,
        name: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> User:
        # Read both accounts from the database so permission decisions use
        # their current roles, not values displayed by the interface.
        actor = self.user_repository.get_by_id(actor_id)
        target = self.user_repository.get_by_id(target_id)

        if actor is None or not actor.is_active:
            raise PermissionError("An active staff account is required.")

        if target is None:
            raise ValueError("Account not found.")

        # Boss Admins may edit any account. STEAM Specialists may edit their
        # own password or a Work Study Assistant. Assistants may edit only
        # their own account.
        if actor.role == "boss_admin":
            allowed = True
        elif actor.role == "steam_specialist":
            if actor.id == target.id and (name is not None or username is not None):
                raise PermissionError("You can only change your own password.")
            allowed = (
                actor.id == target.id
                or target.role == "base_specialist"
            )
        else:
            allowed = (
                actor.role == "base_specialist"
                and actor.id == target.id
            )

        if not allowed:
            raise PermissionError("You cannot edit this account.")

        # Validate all supplied values before changing the account.
        if name is not None:
            name = name.strip()
            if not name or len(name) > 100:
                raise ValueError(
                    "Name must contain between 1 and 100 characters."
                )

        if username is not None:
            username = username.strip().lower()
            if (
                not username
                or len(username) > 50
                or any(character.isspace() for character in username)
            ):
                raise ValueError(
                    "Username must contain between 1 and 50 characters "
                    "and cannot contain spaces."
                )

        if password is not None and len(password) < 12:
            raise ValueError("Password must contain at least 12 characters.")

        # None means leave that field alone. An entered password is hashed
        # before the updated account is sent to the repository.
        if name is not None:
            target.name = name

        if username is not None:
            target.username = username

        if password is not None:
            target.password_hash = (
                self.password_service.hash_password(password)
            )

        return self.user_repository.update(target)

    def delete_account(self, actor_id: int, target_id: int) -> None:
        # Read current account roles before deciding whether deletion is allowed.
        actor = self.user_repository.get_by_id(actor_id)
        target = self.user_repository.get_by_id(target_id)

        if actor is None or not actor.is_active:
            raise PermissionError("An active staff account is required.")

        if target is None:
            raise ValueError("Account not found.")

        # STEAM Specialists may delete Work Study Assistant accounts only.
        if actor.role == "boss_admin":
            allowed = True
        elif actor.role == "steam_specialist":
            allowed = (
                actor.id != target.id
                and target.role == "base_specialist"
            )
        else:
            allowed = False

        if not allowed:
            raise PermissionError("You cannot delete this account.")

        # Never remove the only active Boss Admin. Another active Boss Admin
        # must exist before this account can be deleted.
        if target.role == "boss_admin" and target.is_active:
            active_bosses = [
                user
                for user in self.user_repository.get_all()
                if user.role == "boss_admin" and user.is_active
            ]

            if len(active_bosses) <= 1:
                raise PermissionError(
                    "The last active Boss Admin cannot be deleted."
                )

        # The caller commits or rolls back the database transaction.
        self.user_repository.delete(target)

    def change_role(
        self,
        actor_id: int,
        target_id: int,
        new_role: str,
    ) -> User:
        # Check the actor's current database role rather than the UI label.
        actor = self.user_repository.get_by_id(actor_id)
        target = self.user_repository.get_by_id(target_id)

        if actor is None or not actor.is_active:
            raise PermissionError("An active Boss Admin is required.")

        if actor.role != "boss_admin":
            raise PermissionError(
                "Only a Boss Admin can change account roles."
            )

        if target is None:
            raise ValueError("Account not found.")

        if new_role not in VALID_ROLES:
            raise ValueError("Unknown account role.")

        # There is nothing to save when the requested role is already set.
        if target.role == new_role:
            return target

        # Removing Boss Admin status requires another active Boss Admin.
        if target.role == "boss_admin" and target.is_active:
            active_bosses = [
                user
                for user in self.user_repository.get_all()
                if user.role == "boss_admin" and user.is_active
            ]

            if len(active_bosses) <= 1:
                raise PermissionError(
                    "The last active Boss Admin cannot lose that role."
                )

        target.role = new_role

        # The caller commits or rolls back the database transaction.
        return self.user_repository.update(target)
    
