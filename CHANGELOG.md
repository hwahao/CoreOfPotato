# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-06-09

### Added
- Functional Help System (Modals/Popups) for Dashboard sections.
- Expanded Load Test prompt pool to 100 diverse questions with fully randomized selections.

### Fixed
- Fixed bug where Dashboard Uptime stayed at 0 due to property mismatch.
- Fixed bug where Active Count and Queue Count were missing from `/api/status` endpoint.
- Handled queue overflow gracefully in `load_test.py` (Phase 5).

## [1.0.0] - 2026-06-06

### Added
- Open-source release of CoreNexus.
- Complete integration with **CloakBrowser** for advanced stealth browser automation.
- Headless toggle feature for easier debugging and observation.
- API Gateway for unified access to browser-automated workflows.
- Clean separation of concerns with an extensible driver architecture.
- New `setup.sh` and configuration management (`config.example.json`).
- Automated CI pipeline using GitHub Actions with `pytest` and `ruff`.

[1.0.0]: https://github.com/hwahao/CoreNexus/releases/tag/v1.0.0

