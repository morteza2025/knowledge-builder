"""
Detects text that has already been corrupted by an encoding mismatch before
it reached this process — most commonly Persian text typed into a Windows
terminal whose active codepage isn't UTF-8, so non-ASCII characters get
replaced with literal '?' before curl/requests ever sends the bytes.

By the time the string reaches Python it's already lossy; there is nothing
to "fix" here. The goal is only to fail loudly with a clear, actionable
message instead of silently writing "???? ???" into a JSON file, which is
what happened before this rebuild.
"""

import re

from app.core.exceptions import SuspiciousEncodingError

# A run of 2+ literal question marks where readable text is expected is the
# telltale sign of the CMD/PowerShell default-codepage problem. A single '?'
# can be legitimate punctuation, so we only flag repeated runs.
_SUSPICIOUS_PATTERN = re.compile(r"\?{2,}")


def assert_clean_text(value: str, field_name: str) -> str:
    if value and _SUSPICIOUS_PATTERN.search(value):
        raise SuspiciousEncodingError(
            f"'{field_name}' looks like it was corrupted before reaching the "
            f"API (got: {value!r}). This is almost always a non-UTF-8 "
            "terminal codepage on the client side, not a bug in this "
            "service. Fixes: (1) send the request from a UTF-8-safe client "
            "(e.g. Python 'requests', not raw curl in Windows CMD), or "
            "(2) place a '<pdf-stem>.meta.json' file next to the PDF in the "
            "input directory with the same fields — see README.md."
        )
    return value
