"""
Unit tests for DITA utility functions.
"""
import pytest
from app.generator.dita_utils import make_dita_id, is_valid_dita_id, DITA_ID_PATTERN


class TestMakeDitaId:
    """Test make_dita_id function."""
    
    def test_starts_with_letter(self):
        """Test that IDs starting with letters are valid."""
        used = set()
        result = make_dita_id("topic1", "t", used)
        assert result.startswith(('t', 'T', 'topic'))
        assert is_valid_dita_id(result)
    
    def test_starts_with_digit_adds_prefix(self):
        """Test that IDs starting with digits get prefix."""
        used = set()
        result = make_dita_id("123topic", "t", used)
        assert result.startswith("t_")
        assert is_valid_dita_id(result)
        assert not result.startswith(('0', '1', '2', '3', '4', '5', '6', '7', '8', '9'))
    
    def test_sanitizes_invalid_chars(self):
        """Test that invalid characters are replaced with underscore."""
        used = set()
        result = make_dita_id("topic@#$%", "t", used)
        assert '@' not in result
        assert '#' not in result
        assert '$' not in result
        assert '%' not in result
        assert is_valid_dita_id(result)
    
    def test_collapses_multiple_underscores(self):
        """Test that multiple underscores are collapsed."""
        used = set()
        result = make_dita_id("topic___test", "t", used)
        assert '___' not in result
        assert is_valid_dita_id(result)
    
    def test_ensures_uniqueness(self):
        """Test that uniqueness is ensured with suffix."""
        used = set()
        id1 = make_dita_id("topic", "t", used)
        id2 = make_dita_id("topic", "t", used)
        assert id1 != id2
        assert id2.endswith("_1")
        assert is_valid_dita_id(id1)
        assert is_valid_dita_id(id2)
    
    def test_max_length_enforced(self):
        """Test that max length is enforced."""
        used = set()
        long_input = "a" * 100
        result = make_dita_id(long_input, "t", used)
        assert len(result) <= 80
        assert is_valid_dita_id(result)
    
    def test_empty_string_uses_prefix(self):
        """Test that empty string uses prefix."""
        used = set()
        result = make_dita_id("", "t", used)
        assert result.startswith("t")
        assert is_valid_dita_id(result)
    
    def test_allows_valid_chars(self):
        """Test that valid characters are preserved."""
        used = set()
        result = make_dita_id("topic_123-test.abc", "t", used)
        assert '_' in result or '-' in result or '.' in result
        assert is_valid_dita_id(result)


class TestIsValidDitaId:
    """Test is_valid_dita_id function."""
    
    def test_valid_ids(self):
        """Test valid DITA IDs."""
        assert is_valid_dita_id("topic1")
        assert is_valid_dita_id("topic_123")
        assert is_valid_dita_id("topic-test")
        assert is_valid_dita_id("topic.test")
        assert is_valid_dita_id("_topic")
        assert is_valid_dita_id("Topic123")
    
    def test_invalid_ids(self):
        """Test invalid DITA IDs."""
        assert not is_valid_dita_id("123topic")
        assert not is_valid_dita_id("")
        assert not is_valid_dita_id("topic@test")
        assert not is_valid_dita_id("topic#test")
        assert not is_valid_dita_id("topic$test")
        assert not is_valid_dita_id("topic%test")
        assert not is_valid_dita_id("topic test")
        assert not is_valid_dita_id("topic\ntest")
    
    def test_max_length(self):
        """Test that max length is checked."""
        long_id = "a" * 81
        assert not is_valid_dita_id(long_id)
        short_id = "a" * 80
        assert is_valid_dita_id(short_id)


class TestDitaIdPattern:
    """Test DITA ID regex pattern."""
    
    def test_pattern_matches_valid(self):
        """Test pattern matches valid IDs."""
        assert DITA_ID_PATTERN.match("topic1")
        assert DITA_ID_PATTERN.match("topic_123")
        assert DITA_ID_PATTERN.match("topic-test")
        assert DITA_ID_PATTERN.match("topic.test")
        assert DITA_ID_PATTERN.match("_topic")
        assert DITA_ID_PATTERN.match("Topic123")
    
    def test_pattern_rejects_invalid(self):
        """Test pattern rejects invalid IDs."""
        assert not DITA_ID_PATTERN.match("123topic")
        assert not DITA_ID_PATTERN.match("topic@test")
        assert not DITA_ID_PATTERN.match("topic#test")
        assert not DITA_ID_PATTERN.match("topic test")
