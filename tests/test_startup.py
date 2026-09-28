# Tests that the SAGE window opens, has the correct title, and closes without errors.
import unittest
from PySide6.QtWidgets import QApplication
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


if __name__ == "__main__":
    # Run the tests if this file is started directly.
    unittest.main()