# Tests SAGE's starting mode and transitions between account modes.

import unittest

from services.session_service import SessionService


class TestSessionService(unittest.TestCase):
    def setUp(self):
        self.service = SessionService()

    # Tests that a new SAGE session starts in Student Mode without a user.
    def test_start_defaults_to_student(self):
        state = self.service.start()

        self.assertEqual(state.mode, "student")
        self.assertEqual(state.button_label, "Student Mode")
        self.assertIsNone(state.user_id)
        self.assertIsNone(state.user_name)

    # Tests that a successful Boss Admin login sets the account identity.
    def test_login_sets_admin_mode(self):
        state = self.service.log_in(1, "Test Boss", "boss_admin")

        self.assertEqual(state.mode, "boss_admin")
        self.assertEqual(state.button_label, "Boss Admin")
        self.assertEqual(state.user_id, 1)
        self.assertEqual(state.user_name, "Test Boss")

    # Tests that logout removes the account and restores Student Mode.
    def test_logout_restores_student_mode(self):
        self.service.log_in(1, "Test Boss", "boss_admin")

        state = self.service.log_out()

        self.assertEqual(state.mode, "student")
        self.assertIsNone(state.user_id)
        self.assertEqual(state.button_label, "Student Mode")

    # Tests that an unrecognized account role cannot become an active mode.
    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.log_in(1, "Test User", "unknown_role")


if __name__ == "__main__":
    unittest.main()