from unittest.mock import patch

import pytest

from database import setup_admin


@pytest.mark.parametrize("name,username,password,confirmation,message", [
    ("", "user", "valid-password", "valid-password", "Name must contain"),
    ("x" * 101, "user", "valid-password", "valid-password", "Name must contain"),
    ("User", "", "valid-password", "valid-password", "Username must contain"),
    ("User", "x" * 51, "valid-password", "valid-password", "Username must contain"),
    ("User", "two words", "valid-password", "valid-password", "Username cannot contain spaces."),
    ("User", "user", "short", "short", "Password must contain"),
    ("User", "user", "valid-password", "different", "Passwords do not match"),
    (" User ", " USER ", "valid-password", "valid-password", "created successfully"),
])
def test_setup_cli_validation_and_normalization(capsys, name, username, password, confirmation, message):
    with patch.object(setup_admin, "SessionLocal"), patch.object(setup_admin, "UserRepository") as repositories, \
            patch.object(setup_admin, "PasswordService") as passwords, \
            patch("builtins.input", side_effect=[name, username]), \
            patch.object(setup_admin, "getpass", side_effect=[password, confirmation]):
        repository = repositories.return_value
        repository.get_all.return_value = []
        passwords.return_value.hash_password.return_value = "test-hash"
        setup_admin.main()
        output = capsys.readouterr().out
        assert message in output
        assert password not in output
        if "created successfully" in message:
            user = repository.add.call_args.args[0]
            assert (user.name, user.username, user.role, user.password_hash) == (
                "User", "user", "boss_admin", "test-hash")
        else:
            repository.add.assert_not_called()


def test_existing_accounts_cancel_before_prompting(capsys):
    with patch.object(setup_admin, "SessionLocal"), patch.object(setup_admin, "UserRepository") as repositories, \
            patch("builtins.input") as prompt:
        repositories.return_value.get_all.return_value = [object()]
        setup_admin.main()
        prompt.assert_not_called()
        assert "already exist" in capsys.readouterr().out
