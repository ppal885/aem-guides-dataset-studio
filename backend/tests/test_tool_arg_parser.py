"""Tests for tool_arg_parser — JSON repair and validation."""
import pytest
from app.services.tool_arg_parser import parse_tool_arguments, repair_truncated_json


class TestParseToolArguments:
    def test_valid_json_passthrough(self):
        args, err = parse_tool_arguments('{"text": "hello", "count": 5}', "test_tool")
        assert err is None
        assert args == {"text": "hello", "count": 5}

    def test_empty_string_returns_empty_dict(self):
        args, err = parse_tool_arguments("", "test_tool")
        assert err is None
        assert args == {}

    def test_whitespace_only_returns_empty_dict(self):
        args, err = parse_tool_arguments("   ", "test_tool")
        assert err is None
        assert args == {}

    def test_none_returns_empty_dict(self):
        args, err = parse_tool_arguments(None, "test_tool")
        assert err is None
        assert args == {}

    def test_non_dict_json_returns_error(self):
        args, err = parse_tool_arguments('[1, 2, 3]', "test_tool")
        assert args == {}
        assert "expected object" in err.lower()

    def test_truncated_json_repaired(self):
        # Simulate Groq streaming truncation
        args, err = parse_tool_arguments('{"text": "hello wor', "generate_dita")
        assert err is None
        assert args["text"] == "hello wor"

    def test_truncated_nested_object(self):
        args, err = parse_tool_arguments('{"config": {"count": 5', "create_job")
        assert err is None
        assert args["config"]["count"] == 5

    def test_truncated_array(self):
        args, err = parse_tool_arguments('{"items": ["a", "b"', "test_tool")
        assert err is None
        assert args["items"] == ["a", "b"]

    def test_trailing_comma_repaired(self):
        args, err = parse_tool_arguments('{"a": 1,', "test_tool")
        assert err is None
        assert args["a"] == 1

    def test_garbled_json_returns_error(self):
        args, err = parse_tool_arguments("not json at all", "test_tool")
        assert args == {}
        assert err is not None
        assert "malformed" in err.lower()

    def test_repair_disabled(self):
        args, err = parse_tool_arguments(
            '{"text": "truncated', "test_tool", attempt_repair=False
        )
        assert args == {}
        assert err is not None


class TestRepairTruncatedJson:
    def test_already_valid(self):
        result = repair_truncated_json('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_unclosed_string(self):
        result = repair_truncated_json('{"key": "val')
        assert result is not None
        assert result.endswith('"}')

    def test_unclosed_object(self):
        result = repair_truncated_json('{"key": "value"')
        assert result is not None
        assert result.endswith("}")

    def test_unclosed_array_in_object(self):
        result = repair_truncated_json('{"items": ["a", "b"')
        assert result is not None
        assert result.endswith("]}")

    def test_empty_string_returns_none(self):
        assert repair_truncated_json("") is None
        assert repair_truncated_json(None) is None

    def test_non_object_returns_none(self):
        assert repair_truncated_json("[1, 2") is None

    def test_deeply_nested(self):
        result = repair_truncated_json('{"a": {"b": {"c": "d"')
        assert result is not None
        # Should close string + 3 objects
        import json
        parsed = json.loads(result)
        assert parsed["a"]["b"]["c"] == "d"


class TestParseInlineFunctionXml:
    """Test Groq/Llama inline <function> XML recovery."""

    def test_basic_function_xml(self):
        from app.services.llm_service import _parse_inline_function_xml
        text = '<function name="generate_dita" parameters="{&quot;text&quot;: &quot;Using Rest API&quot;}" />'
        blocks = _parse_inline_function_xml(text)
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0]["name"] == "generate_dita"
        assert blocks[0]["input"]["text"] == "Using Rest API"

    def test_no_function_xml(self):
        from app.services.llm_service import _parse_inline_function_xml
        text = "I'll help you generate a DITA topic about REST APIs."
        blocks = _parse_inline_function_xml(text)
        assert blocks is None

    def test_function_with_multiple_params(self):
        from app.services.llm_service import _parse_inline_function_xml
        text = '<function name="generate_dita" parameters="{&quot;text&quot;: &quot;API guide&quot;, &quot;instructions&quot;: &quot;include examples&quot;}" />'
        blocks = _parse_inline_function_xml(text)
        assert blocks is not None
        assert blocks[0]["input"]["text"] == "API guide"
        assert blocks[0]["input"]["instructions"] == "include examples"

    def test_function_with_empty_params(self):
        from app.services.llm_service import _parse_inline_function_xml
        text = '<function name="generate_dita" parameters="{&quot;instructions&quot;: &quot;&quot;, &quot;text&quot;: &quot;hello&quot;}" />'
        blocks = _parse_inline_function_xml(text)
        assert blocks is not None
        assert blocks[0]["input"]["text"] == "hello"
        assert blocks[0]["input"]["instructions"] == ""

    def test_text_surrounding_function(self):
        from app.services.llm_service import _parse_inline_function_xml
        text = 'Sure, let me do that for you.\n<function name="generate_dita" parameters="{&quot;text&quot;: &quot;test&quot;}" />\n'
        blocks = _parse_inline_function_xml(text)
        assert blocks is not None
        assert blocks[0]["name"] == "generate_dita"
