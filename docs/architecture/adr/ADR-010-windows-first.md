# ADR-010: Windows-first

- **Status:** Accepted
- **Context:** The builder works on Windows 11. Windows has its own attack surface (binary planting from the current directory, `.bat` re-parsing, junctions, 8.3 names, ADS, device names) that most agents ignore.
- **Decision:** Build and test on Windows first: CONIN$ approvals, `creationflags` + job objects, `NoDefaultCurrentDirectoryInExePath`, Windows path normalisation, Credential Manager for secrets, and the `%APPDATA%` / `%LOCALAPPDATA%` / `%PROGRAMDATA%` layout. Keep console input behind one `ask()` function so a `/dev/tty` backend can be added (P1), and run CI on windows + ubuntu for the platform-neutral tests.
- **Consequences:** + A real Windows security story that matches the demo machine. − Judges on macOS/Linux may not run everything; mitigated by the video, CI and a documented quickstart. mini-swe-agent runs in WSL2.
