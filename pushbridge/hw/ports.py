# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Fancy Butler
"""Port description shared by the Linux (ALSA) and Windows (WinMM) backends."""
from __future__ import annotations

from dataclasses import dataclass

CAP_READ, CAP_WRITE = 1, 2


@dataclass
class PortInfo:
    client: int
    port: int
    client_name: str
    name: str
    caps: int

    @property
    def addr(self) -> tuple[int, int]:
        return self.client, self.port


def is_push1(name: str) -> bool:
    """Ableton Push 1, and not a Push 2/3 or our own port."""
    n = name.lower()
    return "push" in n and "push 2" not in n and "push2" not in n and "push 3" not in n \
        and "push bridge" not in n
