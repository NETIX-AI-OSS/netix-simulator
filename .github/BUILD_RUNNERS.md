# Build worker requirements

All jobs select NETIX build workers. Docker-dependent Linux jobs select runner group `default`; the unrelated `e2e-worker` group has no Docker and cannot initialize job containers. Native macOS/Windows host jobs select their platform labels without restricting the runner group. No job falls back to a GitHub-hosted runner.

- `[build-only, Linux, X64]`: Linux x86_64 workers need Docker job-container support. Rust/GUI dependencies install inside the job container; host sudo is not required. Docker image workflows additionally need a working Docker daemon and Buildx.
- `[build-only, Linux, ARM64]`: native Linux ARM64 worker required for the existing ARM64 release/image targets. These jobs do not claim that an x86 worker can execute ARM64 without an emulator.
- `[build-only-windows, Windows, X64]`: native Windows x86_64 worker with PowerShell, Git, Rustup, MSVC Build Tools/Windows SDK, CMake and Perl. Existing signing jobs still require their release environment and Azure OIDC configuration.
- `[build-only, macOS]`: native macOS worker with Xcode Command Line Tools, Rustup, Homebrew, CMake and Perl for both existing Darwin targets. Linux is not substituted for Darwin.

Only the rows used by this repository apply. Runner availability and native-platform provisioning must be verified before merging this change. Release-only packaging/signing is not invoked or claimed validated by a pull-request run. All existing platform targets, test gates, artifacts and signing checks remain in place.
