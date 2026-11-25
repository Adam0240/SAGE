"""Shared pure account validation; callers retain authorization and UI wording."""

USERNAME_MESSAGE = "Username must contain between 1 and 50 characters and cannot contain spaces."


def validated_name(value):
    value = value.strip()
    if not value or len(value) > 100:
        raise ValueError("Name must contain between 1 and 100 characters.")
    return value


def validated_username(value, *, length_message=USERNAME_MESSAGE, spaces_message=USERNAME_MESSAGE):
    value = value.strip().lower()
    if not value or len(value) > 50:
        raise ValueError(length_message)
    if any(character.isspace() for character in value):
        raise ValueError(spaces_message)
    return value


def validate_password(value):
    if len(value) < 12:
        raise ValueError("Password must contain at least 12 characters.")
