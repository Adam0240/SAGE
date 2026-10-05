# Tests that the SAGE window opens, has the correct title, and closes without errors.
import unittest
from PySide6.QtWidgets import QApplication
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from main import SageWindow

class TestStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A QApplication is needed before creating the window.
        # Use the existing one if there is one, otherwise create it for the tests.
        cls.app = QApplication.instance() or QApplication([])

    def test_window_opens_and_closes(self):
        # Create the same window that is used when starting SAGE.
        window = SageWindow()

        # Make sure the window still gets closed if part of the test fails.
        self.addCleanup(window.close)

        # Open the window and give Qt a chance to process the change.
        window.show()
        self.app.processEvents()

        # Check that the window is visible and the title is SAGE.
        self.assertTrue(window.isVisible())
        self.assertEqual(window.windowTitle(), "SAGE")

        # Close the window and process the change.
        window.close()
        self.app.processEvents()

        # Check that the window is no longer visible.
        self.assertFalse(window.isVisible())

    def test_student_mode_is_default(self):
        window = SageWindow()
        self.addCleanup(window.close)

        # Check that the UI starts with the Student Mode label.
        self.assertEqual(window.mode_button.text(), "Student Mode")
        self.assertTrue(window.mode_button.isEnabled())

    def test_application_buttons_are_available(self):
        window = SageWindow()
        self.addCleanup(window.close)

        window.show()
        self.app.processEvents()

        # Check that all three application placeholders are available.
        self.assertEqual(len(window.app_buttons), 3)

        for button in window.app_buttons:
            self.assertTrue(button.isVisible())
            self.assertTrue(button.isEnabled())

    def test_escape_requests_exit(self):
        window = SageWindow()
        self.addCleanup(window.close)

        window.show()
        self.app.processEvents()

        # Replace quit temporarily so the test does not exit the application.
        with patch("main.QApplication.quit") as mock_quit:
            QTest.keyClick(window, Qt.Key.Key_Escape)

            # Check that pressing Escape requests an application exit.
            mock_quit.assert_called_once()


if __name__ == "__main__":
    # Run the tests if this file is started directly.
    unittest.main()