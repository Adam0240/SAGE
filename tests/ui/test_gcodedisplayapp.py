# Tests G-code startup, navigation, preview messages, and image display.

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QListWidget, QLineEdit, QLabel

from sage_apps import gcode_display_print_app as gcode_app


class TestGcodeDisplayApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gcode_dir = self.root / "gcodes"
        self.gcode_dir.mkdir()
        self.thumb_dir = self.root / "thumbnails"
        self.window = gcode_app.GcodeDisplayPrintApp(
            gcode_dir=self.gcode_dir, thumbnail_dir=self.thumb_dir)
        self.addCleanup(self.window.close)

    def write_gcode(self, name="model.gcode", content="G1 X0 Y0\nG1 X10 Y10\n"):
        file_path = self.gcode_dir / name
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def load_files(self, gcode_dir=None):
        # Create a fresh window to exercise the complete startup loading behavior.
        self.window.close()
        self.window = gcode_app.GcodeDisplayPrintApp(
            gcode_dir=self.gcode_dir if gcode_dir is None else gcode_dir,
            thumbnail_dir=self.thumb_dir)
        self.addCleanup(self.window.close)

    # Tests an empty folder displays guidance, disables navigation, and keeps printing unavailable.
    def test_empty_folder_startup(self):
        self.assertEqual(self.window.windowTitle(), "SAGE - 3D Printing")
        self.assertEqual(self.window.gcode_files, [])
        self.assertEqual(self.window.filename_label.text(), "No G-code files found")
        self.assertEqual(self.window.preview_label.text(), "Add G-code files to the selected folder.")
        self.assertFalse(self.window.previous_button.isEnabled())
        self.assertFalse(self.window.next_button.isEnabled())
        self.assertFalse(self.window.previous_shortcut.isEnabled())
        self.assertFalse(self.window.next_shortcut.isEnabled())
        self.assertFalse(self.window.start_print_button.isEnabled())
        self.assertFalse(self.window.file_list_button.isEnabled())

    # Tests a missing folder or a configured path pointing to a file displays a useful message.
    def test_invalid_folder_path(self):
        regular_file = self.root / "not_a_folder"
        regular_file.write_text("content", encoding="utf-8")
        for folder in (self.root / "missing", regular_file):
            with self.subTest(folder=folder):
                self.load_files(folder)
                self.assertEqual(self.window.filename_label.text(), "G-code folder not found")
                self.assertEqual(self.window.preview_label.text(), "Check the G-code folder path.")
                self.assertEqual(self.window.gcode_files, [])

    # Tests a folder access failure is handled without crashing startup.
    def test_inaccessible_folder(self):
        with patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")):
            self.load_files()
        self.assertEqual(self.window.filename_label.text(), "Unable to access G-code folder")
        self.assertEqual(self.window.preview_label.text(), "Check folder access and try again.")

    # Tests discovery accepts mixed-case G-code extensions, sorts names, and ignores folders/other files.
    def test_file_discovery_and_initial_selection(self):
        for name in ("zebra.gcode", "Alpha.GCODE", "middle.gCoDe", "notes.txt"):
            self.write_gcode(name)
        (self.gcode_dir / "folder.gcode").mkdir()
        nested = self.gcode_dir / "nested"
        nested.mkdir()
        (nested / "hidden.gcode").write_text("G1 X1", encoding="utf-8")
        self.load_files()
        self.assertEqual([p.name for p in self.window.gcode_files],
                         ["Alpha.GCODE", "middle.gCoDe", "zebra.gcode"])
        self.assertEqual(self.window.current_file_index, 0)
        self.assertEqual(self.window.filename_label.text(), "Alpha.GCODE")
        self.assertFalse(self.window.preview_label.pixmap().isNull())
        self.assertTrue(self.window.previous_button.isEnabled())
        self.assertTrue(self.window.next_button.isEnabled())
        self.assertTrue(self.window.previous_shortcut.isEnabled())
        self.assertTrue(self.window.next_shortcut.isEnabled())
        self.assertFalse(self.window.start_print_button.isEnabled())

    # Tests a single file shows its preview while disabling unnecessary button and keyboard navigation.
    def test_single_file_navigation_disabled(self):
        self.write_gcode()
        self.load_files()
        self.assertEqual(self.window.filename_label.text(), "model.gcode")
        self.assertFalse(self.window.preview_label.pixmap().isNull())
        self.assertFalse(self.window.previous_button.isEnabled())
        self.assertFalse(self.window.next_button.isEnabled())
        self.assertFalse(self.window.previous_shortcut.isEnabled())
        self.assertFalse(self.window.next_shortcut.isEnabled())

    # Tests clicking either arrow wraps selection and refreshes the matching filename and preview.
    def test_navigation_wraparound(self):
        files = [self.write_gcode(name) for name in ("a.gcode", "b.gcode", "c.gcode")]
        self.load_files()
        with patch.object(self.window, "display_gcode_preview") as preview:
            for button, index in ((self.window.previous_button, 2),
                                  (self.window.next_button, 0),
                                  (self.window.next_button, 1)):
                button.click()
                self.assertEqual(self.window.current_file_index, index)
                self.assertEqual(self.window.filename_label.text(), files[index].name)
                preview.assert_called_with(files[index])
            self.assertEqual(preview.call_count, 3)

    # Tests actual left/right key presses select files through the configured Qt shortcuts.
    def test_keyboard_navigation(self):
        self.write_gcode("a.gcode")
        self.write_gcode("b.gcode")
        self.load_files()
        self.window.show()
        self.window.activateWindow()
        self.window.setFocus()
        self.app.processEvents()
        QTest.keyClick(self.window, Qt.Key.Key_Right)
        self.assertEqual(self.window.filename_label.text(), "b.gcode")
        QTest.keyClick(self.window, Qt.Key.Key_Left)
        self.assertEqual(self.window.filename_label.text(), "a.gcode")

    # Tests navigation handlers safely do nothing when no files are available.
    def test_navigation_without_files(self):
        with patch.object(self.window, "display_gcode_preview") as preview:
            self.window.show_previous_file()
            self.window.show_next_file()
            self.assertEqual(self.window.current_file_index, 0)
            self.assertEqual(self.window.filename_label.text(), "No G-code files found")
            preview.assert_not_called()

    # Tests deleted files, invalid text, and parsing errors replace an old preview with a safe message.
    def test_unreadable_file_clears_previous_preview(self):
        valid_file = self.write_gcode()
        invalid_text = self.gcode_dir / "invalid.gcode"
        invalid_text.write_bytes(b"\xff\xfe\xff")
        for file_path in (self.gcode_dir / "missing.gcode", invalid_text):
            with self.subTest(file=file_path.name):
                self.window.display_gcode_preview(valid_file)
                self.window.display_gcode_preview(file_path)
                self.assertEqual(self.window.preview_label.text(), "Unable to read this G-code file.")
                self.assertTrue(self.window.preview_label.pixmap().isNull())
        with patch("services.gcode_preview_service.read_gcode_coordinates", side_effect=ValueError("Invalid value")):
            self.window.display_gcode_preview(self.gcode_dir / "uncached.gcode")
        self.assertEqual(self.window.preview_label.text(), "Unable to read this G-code file.")

    # Tests files with fewer than two positions show guidance and remove the previous preview.
    def test_insufficient_movement(self):
        valid_file = self.write_gcode()
        for content in ("", "; Comments only\nM104 S200\n", "G1 X10 Y20\n"):
            with self.subTest(content=content):
                self.window.display_gcode_preview(valid_file)
                file_path = self.write_gcode("short.gcode", content)
                self.window.display_gcode_preview(file_path)
                self.assertEqual(self.window.preview_label.text(), "No previewable movement found.")
                self.assertTrue(self.window.preview_label.pixmap().isNull())

    # Tests displayed images fit within the preview area while preserving their proportions.
    def test_preview_image_scaling(self):
        self.window.preview_label.resize(400, 300)
        image = QImage(800, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        self.window.show_preview_image(image)
        pixmap = self.window.preview_label.pixmap()
        available = self.window.preview_label.contentsRect().size()
        self.assertFalse(pixmap.isNull())
        self.assertLessEqual(pixmap.width(), available.width())
        self.assertLessEqual(pixmap.height(), available.height())
        self.assertAlmostEqual(pixmap.width() / pixmap.height(), 2.0, delta=0.02)

    # Tests omitted folder arguments retain the existing installation defaults.
    def test_default_folder_settings(self):
        with patch.object(gcode_app, "GCODE_DIR", self.gcode_dir), \
                patch.object(gcode_app, "THUMB_DIR", self.thumb_dir):
            window = gcode_app.GcodeDisplayPrintApp()
            self.addCleanup(window.close)
        self.assertEqual(window.gcode_dir, self.gcode_dir)
        self.assertEqual(window.preview_service.thumbnail_dir, self.thumb_dir)

    # Tests a successful service result replaces an earlier error message with its image.
    def test_service_image_is_displayed(self):
        image = QImage(800, 600, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        file_path = self.gcode_dir / "selected.gcode"
        self.window.preview_label.setText("Earlier error")
        with patch.object(self.window.preview_service, "get_preview", return_value=image) as preview:
            self.window.display_gcode_preview(file_path)
            preview.assert_called_once_with(file_path)
        self.assertEqual(self.window.preview_label.text(), "")
        self.assertFalse(self.window.preview_label.pixmap().isNull())

    # Tests the file-list button shows sorted filenames, highlights the current file, and selects on Open.
    def test_file_list_selection_and_navigation(self):
        files = [self.write_gcode(name) for name in ("a.gcode", "b.gcode", "c.gcode")]
        self.load_files()
        self.window.show_previous_file()
        self.assertTrue(self.window.file_list_button.isEnabled())

        def choose_file(dialog):
            file_list = dialog.findChild(QListWidget)
            self.assertEqual([file_list.item(i).text() for i in range(file_list.count())],
                             [file.name for file in files])
            self.assertEqual(file_list.currentRow(), 2)
            file_list.setCurrentRow(1)
            buttons = dialog.findChild(QDialogButtonBox)
            buttons.button(QDialogButtonBox.StandardButton.Open).click()
            return dialog.result()

        with patch.object(QDialog, "exec", new=choose_file), \
                patch.object(self.window.preview_service, "get_preview",
                             wraps=self.window.preview_service.get_preview) as preview:
            self.window.file_list_button.click()
            preview.assert_called_once_with(files[1])
        self.assertEqual(self.window.current_file_index, 1)
        self.assertEqual(self.window.filename_label.text(), "b.gcode")
        self.assertFalse(self.window.preview_label.pixmap().isNull())
        self.window.next_button.click()
        self.assertEqual(self.window.filename_label.text(), "c.gcode")

    # Tests cancelling or closing the list after changing its highlighted row preserves selection and preview.
    def test_file_list_cancel_keeps_selection(self):
        self.write_gcode("a.gcode")
        self.write_gcode("b.gcode")
        self.load_files()
        original_preview = self.window.preview_label.pixmap().cacheKey()

        for action in ("cancel", "close"):
            with self.subTest(action=action):
                def dismiss(dialog):
                    dialog.findChild(QListWidget).setCurrentRow(1)
                    if action == "cancel":
                        dialog.findChild(QDialogButtonBox).button(
                            QDialogButtonBox.StandardButton.Cancel).click()
                    else:
                        dialog.close()
                    return dialog.result()

                with patch.object(QDialog, "exec", new=dismiss), \
                        patch.object(self.window.preview_service, "get_preview") as preview:
                    self.window.file_list_button.click()
                    preview.assert_not_called()
                self.assertEqual(self.window.current_file_index, 0)
                self.assertEqual(self.window.filename_label.text(), "a.gcode")
                self.assertEqual(self.window.preview_label.pixmap().cacheKey(), original_preview)

    # Tests activating a list item confirms the selection for double-click and keyboard activation.
    def test_file_list_item_activation(self):
        self.write_gcode("a.gcode")
        self.write_gcode("b.gcode")
        self.load_files()

        def activate(dialog):
            file_list = dialog.findChild(QListWidget)
            file_list.setCurrentRow(1)
            file_list.itemActivated.emit(file_list.currentItem())
            return dialog.result()

        with patch.object(QDialog, "exec", new=activate):
            self.window.file_list_button.click()
        self.assertEqual(self.window.filename_label.text(), "b.gcode")

    # Tests an empty file list cannot open a dialog through either the button or direct handler.
    def test_file_list_without_files(self):
        with patch.object(QDialog, "exec", autospec=True) as execute:
            self.window.file_list_button.click()
            self.window.show_file_list()
            execute.assert_not_called()

    # Tests selecting a file deleted since discovery displays the existing unreadable-file message.
    def test_file_list_deleted_file(self):
        self.write_gcode("a.gcode")
        removed = self.write_gcode("b.gcode")
        self.load_files()
        removed.unlink()

        def choose_deleted(dialog):
            dialog.findChild(QListWidget).setCurrentRow(1)
            dialog.accept()
            return dialog.result()

        with patch.object(QDialog, "exec", new=choose_deleted):
            self.window.file_list_button.click()
        self.assertEqual(self.window.filename_label.text(), "b.gcode")
        self.assertEqual(self.window.preview_label.text(), "Unable to read this G-code file.")
        self.assertTrue(self.window.preview_label.pixmap().isNull())

    # Tests typing filters filenames by partial, case-insensitive matches and opens the original file index.
    def test_file_list_search_match(self):
        self.write_gcode("a.gcode")
        matching_file = self.write_gcode("Robot_Model.GCODE")
        self.write_gcode("z.gcode")
        self.load_files()

        def search_and_open(dialog):
            search = dialog.findChild(QLineEdit)
            QTest.keyClicks(search, "rObOt")
            file_list = dialog.findChild(QListWidget)
            visible = [file_list.item(row).text() for row in range(file_list.count())
                       if not file_list.item(row).isHidden()]
            self.assertEqual(visible, [matching_file.name])
            self.assertEqual(file_list.currentRow(), 1)
            dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Open).click()
            return dialog.result()

        with patch.object(QDialog, "exec", new=search_and_open), \
                patch.object(self.window.preview_service, "get_preview",
                             wraps=self.window.preview_service.get_preview) as preview:
            self.window.show_file_list()
            preview.assert_called_once_with(matching_file)
        self.assertEqual(self.window.current_file_index, 1)
        self.assertEqual(self.window.filename_label.text(), matching_file.name)

    # Tests unmatched searches disable Open, display guidance, and cannot replace the current preview.
    def test_file_list_search_no_matches(self):
        self.write_gcode()
        self.load_files()
        original_preview = self.window.preview_label.pixmap().cacheKey()

        def no_matches(dialog):
            dialog.findChild(QLineEdit).setText("missing model")
            self.assertEqual(dialog.findChild(QListWidget).currentRow(), -1)
            self.assertFalse(dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Open).isEnabled())
            self.assertFalse(dialog.findChild(QLabel, "no_matches_label").isHidden())
            # Even a forced acceptance must not open a hidden or missing selection.
            dialog.accept()
            return dialog.result()

        with patch.object(QDialog, "exec", new=no_matches), \
                patch.object(self.window.preview_service, "get_preview") as preview:
            self.window.show_file_list()
            preview.assert_not_called()
        self.assertEqual(self.window.filename_label.text(), "model.gcode")
        self.assertEqual(self.window.preview_label.pixmap().cacheKey(), original_preview)

    # Tests clearing a search restores every file and Open, while cancelling preserves the app selection.
    def test_file_list_search_reset(self):
        self.write_gcode("a.gcode")
        self.write_gcode("robot.gcode")
        self.load_files()

        def search_clear_cancel(dialog):
            search = dialog.findChild(QLineEdit)
            file_list = dialog.findChild(QListWidget)
            search.setText("  ROBOT  ")
            self.assertTrue(file_list.item(0).isHidden())
            self.assertFalse(file_list.item(1).isHidden())
            search.setText("no match")
            search.clear()
            self.assertTrue(all(not file_list.item(row).isHidden()
                                for row in range(file_list.count())))
            self.assertTrue(dialog.findChild(QLabel, "no_matches_label").isHidden())
            self.assertTrue(dialog.findChild(QDialogButtonBox).button(
                QDialogButtonBox.StandardButton.Open).isEnabled())
            dialog.reject()
            return dialog.result()

        with patch.object(QDialog, "exec", new=search_clear_cancel), \
                patch.object(self.window.preview_service, "get_preview") as preview:
            self.window.show_file_list()
            preview.assert_not_called()
        self.assertEqual(self.window.current_file_index, 0)
        self.assertEqual(self.window.filename_label.text(), "a.gcode")
