# Agent.md file I created specifically for SAGE so codex can perform full code reviews after a change has been implemented

Perform a full, read-only code review of this SAGE repository

Review the application code, database model and migration, repository and services, PySide6 UI and login threading, tests, Docker Compose configuration, requirements, README, and comments. Look for correctness bugs, security or permission problems, UI freezes, missing or undiscovered tests, outdated documentation, and unnecessary code. Check whether the current implementation supports the Initializing SAGE use case.

Run the existing tests if the required environment is already available. Do not start Docker, change the database, install dependencies, or claim tests passed if they could not be run.

Write the results to a new file named code_review.md in the repository root. Include:
1. A brief review summary and the files reviewed.
2. Findings ordered by severity, each with a file and line number, the problem, its impact, and a specific suggested fix.
3. Test results, including tests that were skipped or could not be run.
4. Issue #10 checklist items that are supported by evidence, and items still open.
5. Any findings that can reasonably be deferred to later issues.
6. Be sure comments are included where appropriate, and inform me of any commented out code that should be removed.

Do not edit any existing files. Do not commit, push, create branches or pull requests, or change GitHub issues or the Kanban board. Creating code_review.md is the only authorized change. Tell me when it is ready and summarize the most important findings in chat.