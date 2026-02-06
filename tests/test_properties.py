import hypothesis.strategies as st
from hypothesis import given
from yt_study.core.telemetry import redact_pii
from yt_study.utils import sanitize_filename
import os
from pathlib import Path

@given(st.text())
def test_redact_pii_never_crashes(s):
    redact_pii(s)

@given(st.dictionaries(st.text(), st.text()))
def test_redact_pii_dict_never_crashes(d):
    redact_pii(d)

@given(st.text())
def test_redact_pii_redacts_home(s):
    home = str(Path.home())
    test_str = f"prefix {home} suffix"
    redacted = redact_pii(test_str)
    assert home not in redacted
    assert "<HOME>" in redacted

@given(st.text(min_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')))
def test_redact_pii_redacts_potential_keys(key):
    # Ensure we only test keys that the regex is intended to catch (alphanumeric)
    # The implementation uses [a-zA-Z0-9]{20,}
    if not all(c.isalnum() and ord(c) < 128 for c in key):
        return

    test_str = f"api_key: {key}"
    redacted = redact_pii(test_str)
    assert key not in redacted
    assert "<REDACTED>" in redacted

@given(st.text())
def test_sanitize_filename_never_crashes(s):
    sanitized = sanitize_filename(s)
    assert isinstance(sanitized, str)
    assert len(sanitized) > 0

def test_sanitize_filename_known_patterns():
    assert sanitize_filename("con") != "con" # Windows reserved
    assert sanitize_filename("test/file") == "test_file"
    assert sanitize_filename("  test  file  ") == "test file"
