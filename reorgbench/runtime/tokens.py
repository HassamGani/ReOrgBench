"""Reference tokenizer for context accounting (Π, token caps).

v0 is a fixed character heuristic so counts are identical across providers. Swap for a real
pinned tokenizer before the first release; changing it is a version bump.
"""

from __future__ import annotations

import json
import math
from typing import Any

TOKENIZER_ID = "chars4-v0"


def count_tokens(x: Any) -> int:
    s = x if isinstance(x, str) else json.dumps(x, sort_keys=True)
    return math.ceil(len(s) / 4) if s else 0
