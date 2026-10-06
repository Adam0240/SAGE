# Run Qt tests without opening visible windows while preserving an explicit platform setting.

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
