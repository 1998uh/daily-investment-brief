from agent.llm import _extract_stream_delta, _parse_stream_line


def test_extracts_openai_compatible_stream_delta():
    data = _parse_stream_line(
        "openai",
        'data: {"choices":[{"delta":{"content":"hello"}}]}',
    )
    assert _extract_stream_delta("openai", data) == "hello"


def test_extracts_openai_responses_stream_delta():
    data = _parse_stream_line(
        "openai-responses",
        'data: {"type":"response.output_text.delta","delta":"hello"}',
    )
    assert _extract_stream_delta("openai-responses", data) == "hello"


def test_extracts_anthropic_stream_delta():
    data = _parse_stream_line(
        "anthropic",
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hello"}}',
    )
    assert _extract_stream_delta("anthropic", data) == "hello"


def test_extracts_gemini_stream_delta():
    data = _parse_stream_line(
        "gemini",
        'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}',
    )
    assert _extract_stream_delta("gemini", data) == "hello"


def test_extracts_ollama_ndjson_stream_delta():
    data = _parse_stream_line(
        "ollama",
        '{"message":{"role":"assistant","content":"hello"},"done":false}',
    )
    assert _extract_stream_delta("ollama", data) == "hello"
