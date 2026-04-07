"""Subprocess lifecycle management for ptp4l and phc2sys."""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
from typing import Callable, Dict, List, Optional

log = logging.getLogger(__name__)


class ManagedProcess:
    """Wraps a single subprocess with log streaming and restart capability."""

    def __init__(
        self,
        name: str,
        cmd: List[str],
        log_prefix: str = "",
        line_callback: Optional[Callable[[str], None]] = None,
    ):
        self.name = name
        self.cmd = cmd
        self.log_prefix = log_prefix or name
        self._line_callback = line_callback
        self._proc: Optional[subprocess.Popen] = None
        self._log_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        log.info("[%s] Starting: %s", self.name, " ".join(self.cmd))
        self._proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._log_thread = threading.Thread(
            target=self._stream_logs,
            daemon=True,
            name=f"log-{self.name}",
        )
        self._log_thread.start()
        log.info("[%s] Started (pid=%d)", self.name, self._proc.pid)

    def _stream_logs(self) -> None:
        assert self._proc is not None
        for raw in self._proc.stdout:  # type: ignore[union-attr]
            line = raw.rstrip()
            log.info("[%s] %s", self.log_prefix, line)
            if self._line_callback:
                try:
                    self._line_callback(line)
                except Exception:
                    pass

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self, timeout: int = 5) -> None:
        if self._proc and self.is_running():
            log.info("[%s] Stopping (pid=%d)", self.name, self._proc.pid)
            self._proc.terminate()
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning("[%s] Graceful stop timed out, killing", self.name)
                self._proc.kill()
                self._proc.wait()

    @property
    def returncode(self) -> Optional[int]:
        return self._proc.returncode if self._proc else None


class ProcessManager:
    """Manages a set of ManagedProcesses and handles signals."""

    def __init__(self) -> None:
        self._procs: Dict[str, ManagedProcess] = {}
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, _frame) -> None:
        log.info("Signal %d received — shutting down", signum)
        self.stop_all()
        sys.exit(0)

    def add(self, proc: ManagedProcess) -> None:
        self._procs[proc.name] = proc

    def start_all(self) -> None:
        for proc in self._procs.values():
            proc.start()

    def stop_all(self) -> None:
        for proc in reversed(list(self._procs.values())):
            proc.stop()

    def any_exited(self) -> Optional[str]:
        """Return the name of the first process that is no longer running."""
        for name, proc in self._procs.items():
            if not proc.is_running():
                return name
        return None

    def get(self, name: str) -> Optional[ManagedProcess]:
        return self._procs.get(name)
