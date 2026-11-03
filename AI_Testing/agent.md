# Agent.md file I created specifically for SAGE so codex can perform full code reviews after a change has been implemented

Perform a full, read-only code review of this SAGE repository

Review the application code, repository and services, PySide6 UI and login threading, tests, requirements, README, and comments. Look for correctness bugs, security or permission problems, UI freezes, missing or undiscovered tests, duplication, outdated documentation, and unnecessary code. 

Run the existing tests if the required environment is already available. Do not start Docker, change the database, install dependencies, or claim tests passed if they could not be run.

Write the results in the  code_review.md file in the ai_testing folder. Include:
1. A brief review summary and the files reviewed.
2. Findings ordered by severity, each with a file and line number, the problem, its impact, and a specific suggested fix.
3. Test results, including tests that were skipped or could not be run.

Do not edit any existing files. Do not commit, push, create branches or pull requests, or change GitHub issues or the Kanban board. Creating code_review.md is the only authorized change. Tell me when it is ready and summarize the most important findings in chat.