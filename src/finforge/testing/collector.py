"""Pytest plugin to capture test outcomes without modifying developer configuration."""

from __future__ import annotations

from typing import Any


class PytestResultCollector:
    """In-memory Pytest plugin to intercept test counts and failure reports."""

    def __init__(self) -> None:
        self.passed: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self.collection_errors: int = 0
        self.duration_seconds: float = 0.0
        self.failures: list[str] = []

    def pytest_runtest_logreport(self, report: Any) -> None:
        """Capture outcome of individual test execution phases."""
        self.duration_seconds += getattr(report, "duration", 0.0)

        if report.when == "call":
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
                self._record_failure(report)
            elif report.skipped:
                self.skipped += 1
        elif report.when in ("setup", "teardown"):
            # Setup/teardown failures count as test failures
            if report.failed:
                self.failed += 1
                self._record_failure(report)
            elif report.skipped and report.when == "setup":
                # Pytest records skipped tests during setup phase
                self.skipped += 1

    def pytest_collectreport(self, report: Any) -> None:
        """Capture collection errors."""
        if report.failed:
            self.collection_errors += 1
            msg = f"Collection error in {report.nodeid}: {report.longrepr}"
            self.failures.append(str(msg).strip())

    def _record_failure(self, report: Any) -> None:
        """Record formatted failure diagnostics."""
        node_id = getattr(report, "nodeid", "unknown_test")
        longrepr = str(getattr(report, "longrepr", "Test failed"))
        # Truncate overly long error traces for clean display
        lines = longrepr.strip().splitlines()
        short_summary = "\n".join(lines[-10:]) if len(lines) > 10 else longrepr
        self.failures.append(f"{node_id}: {short_summary}")
