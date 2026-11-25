# Changelog

## 2.0.0 — 2026-11

First public release under the name **Silüet** (previously an internal tool called "HTS Anonimleştirici").

### Security
- Phone numbers and national IDs are now fully regenerated. The previous version changed only the last four digits, which left about 10,000 candidates per phone number.
- Generated national IDs always have an invalid checksum.
- The same subscriber written as `0532…`, `90532…`, `+90 532…` or `532…` maps to the same pseudonym.
- The project file is encrypted with a user password (scrypt + AES-256-GCM). Projects from v1 are migrated on open: a backup is taken, the migration is verified, then the plain-text backup is securely deleted.
- OS-level project lock; bounded KDF parameters; masked crash logs.

### Interface
- New PySide6 interface with a sidebar and three steps: Files → Review → Output.
- Turkish and English, light and dark themes.
- Drag-and-drop, content-based pairing, inline role fixes and moving files between groups.
- Continuous pre-run checks, background processing with safe cancel, inline results.

### Distribution
- Windows and Linux builds from CI with launch smoke tests.
- The Linux package does not bundle host system libraries, so it starts on current distributions such as Arch/CachyOS.
