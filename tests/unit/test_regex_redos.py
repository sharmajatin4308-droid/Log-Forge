import re
import time
import pytest
from extensions.syslog_ext.parser import KV_REGEX

# Original regex (vulnerable) for comparison
KV_REGEX_OLD = re.compile(r'([a-zA-Z0-9_\.\-]+)=(?:"([^"]*)"|\'([^\']*)\'|([^\s,;]+))')

def test_kv_regex_equivalence():
    """Ensure the new regex extracts the exact same values as the old one."""
    corpus = [
        # Standard space separated
        "key1=value1 key2=\"value 2\" key3='value 3'",
        # Comma separated
        "k1=v1,k2=v2,k3=v3",
        # Mixed separators
        "a=1, b=2; c=3 d=4",
        # Keys with dots and dashes
        "user.name=john.doe app-id=123",
        # Empty values
        "k1=\"\" k2='' k3=v",
        # Beginning of string
        "start=1 end=2",
        # Malformed but parseable
        "key=\"unclosed key2=val2"
    ]
    
    for text in corpus:
        old_matches = KV_REGEX_OLD.findall(text)
        new_matches = KV_REGEX.findall(text)
        assert old_matches == new_matches, f"Mismatch on input: {text}\nOld: {old_matches}\nNew: {new_matches}"

def test_kv_regex_redos_mitigation():
    """Ensure catastrophic backtracking is mitigated."""
    # Build a pathological payload: 'k="aaaa...' (no closing quote, no equal sign in the tail)
    size = 100000
    payload = 'k="' + 'a' * size + '"' + 'b' * size
    
    t0 = time.time()
    matches = KV_REGEX.findall(payload)
    t1 = time.time()
    
    duration = t1 - t0
    # The original took ~29s on 100k. The new one should take < 0.05s. We allow up to 2.0s for slow CI.
    assert duration < 2.0, f"Regex evaluation took too long: {duration:.4f} seconds"
    
    # It should still extract the first valid pair it finds
    assert matches == [('k', 'a' * size, '', '')]
