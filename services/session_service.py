# Tracks which SAGE mode is active for the current session.

from dataclasses import dataclass


ROLE_LABELS = {
    "boss_admin": "Boss Admin",
    "steam_specialist": "STEAM Specialist",
    "base_specialist": "Work_Study Assistant",
}


@dataclass(frozen=True)
class SessionState:
    mode: str
    user_id: int | None = None
    user_name: str | None = None

    @property
    def button_label(self) -> str:
        if self.mode == "student":
            return "Student Mode"

        return ROLE_LABELS[self.mode]


class SessionService:
    def start(self) -> SessionState:
        # Every launch begins without an administrator logged in.
        return SessionState(mode="student")

    def log_in(
        self,
        user_id: int,
        user_name: str,
        role: str,
    ) -> SessionState:
        # Authentication happens before this method is called.
        if role not in ROLE_LABELS:
            raise ValueError("Unknown SAGE account role.")

        return SessionState(
            mode=role,
            user_id=user_id,
            user_name=user_name,
        )

    def log_out(self) -> SessionState:
        # Returning to Student Mode removes the current account identity.
        return self.start()