# Project Overview

SAGE (STEAM Artificial Guidance Expert) is a Python-based desktop application designed to assist students and staff in the STEAM Room. Its primary purpose is to preserve institutional knowledge, provide equipment instructions and troubleshooting assistance, and provide an interactive interface for accessing STEAM Room resources.

The project is entering its final development and quality assurance phase in preparation for public deployment. The current priority is improving code quality, reliability, and maintainability rather than implementing additional functionality.

# Project Directory Structure

- `main.py` - Application entry point, home screen, application navigation, session management, and service coordination.
- `login_dialog.py` - User authentication interface.
- `sage_apps/` - Application interfaces for account management, the G-code viewer, OctoPrint file browsing, and the STEAM Guide.
- `services/` - Business logic, equipment communication, AI processing, voice interaction, authentication, and background workers.
  - `account_service.py` - Account management and role-based permissions.
  - `authentication_service.py` - User authentication.
  - `password_service.py` - Password hashing and verification.
  - `session_service.py` - Session state and user permissions.
  - `ai_assistant_service.py` - Local Ollama AI assistant.
  - `ai_config.py` - AI configuration.
  - `ai_response_worker.py` - Asynchronous AI response processing.
  - `document_retrieval_service.py` - Local Markdown document retrieval.
  - `guide_response_service.py` - Documentation-based responses and AI fallback behavior.
  - `home_voice_controller.py` - Voice interaction lifecycle and service coordination.
  - `speech_recognition_service.py` - Speech-to-text functionality.
  - `text_to_speech_service.py` - Spoken responses.
  - `voice_command_service.py` - Voice command recognition and routing.
  - `project_search_service.py` - Searching and selecting existing OctoPrint projects.
  - `octoprint_config.py` - OctoPrint configuration and API request preparation.
  - `octoprint_file_service.py` - OctoPrint file retrieval and downloading.
  - `octoprint_print_service.py` - Authorized print initiation.
  - `printer_status_service.py` - Printer connection status and remaining print time.
  - `gcode_parser.py` - G-code parsing.
  - `gcode_preview_service.py` - G-code preview generation and caching.
  - `gcode_preview_worker.py` - Asynchronous preview generation.
- `database/` - PostgreSQL connection management, database models, account operations, repositories, and administrator initialization.
- `migrations/` - Alembic database migrations.
- `TouchControls/` - Webcam-based hand tracking, calibration, dwell interactions, and gesture-based navigation.
- `STEAM_Tutorials/` - Local Markdown documentation used by the STEAM Guide and AI assistant.
- `resources/` - Application icons and other visual resources.
- `tests/` - Automated tests.
  - `tests/unit/` - Individual service and component tests.
  - `tests/ui/` - Application interface, interaction, and service integration tests.
  - `tests/integration/` - Database transactions and concurrency tests.
- `.github/workflows/` - Automated CI/CD pipeline, testing, security scanning, code quality checks, and release packaging.
- `AI_Testing/` - AI-assisted code reviews and analysis documentation.
- `compose.yaml` - Docker configuration for PostgreSQL and Adminer.
- `requirements.txt` - Primary Python dependencies.
- `requirements-speech.txt` - Speech recognition dependencies.
- `.env.example` - Environment configuration template.
- `pytest.ini` - Pytest configuration.
- `.coveragerc` - Automated test coverage configuration.
- `sonar-project.properties` - SonarQube configuration.
- `README.md` - Project overview, installation instructions, and technical documentation.

# Current Task

