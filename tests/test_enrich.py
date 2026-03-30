import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from enrich import load_existing, load_tab, make_prompt, translate


# ---------------------------------------------------------------------------
# make_prompt
# ---------------------------------------------------------------------------


def test_prompt_contains_source_lang():
    prompt = make_prompt("hello", "English (en)", "Sinhala (si)")
    assert "English (en)" in prompt


def test_prompt_contains_target_lang():
    prompt = make_prompt("hello", "English (en)", "Sinhala (si)")
    assert "Sinhala (si)" in prompt


def test_prompt_ends_with_word():
    prompt = make_prompt("cat", "English (en)", "Sinhala (si)")
    assert prompt.endswith("cat")


def test_prompt_reverse_direction():
    prompt = make_prompt("ගෙදර", "Sinhala (si)", "English (en)")
    assert "Sinhala (si)" in prompt
    assert "English (en)" in prompt
    assert prompt.endswith("ගෙදර")


def test_prompt_instructs_no_commentary():
    prompt = make_prompt("hello", "English (en)", "Sinhala (si)")
    assert "without any additional" in prompt


# ---------------------------------------------------------------------------
# load_tab
# ---------------------------------------------------------------------------


def make_tab(content: str) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".tab", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


def test_load_tab_basic():
    path = make_tab("hello\tworld\n")
    try:
        entries = load_tab(path)
        assert entries == [("hello", ["world"])]
    finally:
        os.unlink(path)


def test_load_tab_multiple_definitions():
    path = make_tab("a\tone|two|three\n")
    try:
        entries = load_tab(path)
        assert entries == [("a", ["one", "two", "three"])]
    finally:
        os.unlink(path)


def test_load_tab_skips_empty_lines():
    path = make_tab("hello\tworld\n\nfoo\tbar\n")
    try:
        entries = load_tab(path)
        assert len(entries) == 2
    finally:
        os.unlink(path)


def test_load_tab_skips_lines_without_tab():
    path = make_tab("notabhere\nhello\tworld\n")
    try:
        entries = load_tab(path)
        assert len(entries) == 1
    finally:
        os.unlink(path)


def test_load_tab_sinhala():
    path = make_tab("cat\tපූසා\ndog\tකුකුළා\n")
    try:
        entries = load_tab(path)
        assert entries[0] == ("cat", ["පූසා"])
        assert entries[1] == ("dog", ["කුකුළා"])
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# load_existing
# ---------------------------------------------------------------------------


def make_jsonl(lines: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for line in lines:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    f.close()
    return Path(f.name)


def test_load_existing_returns_words():
    path = make_jsonl([{"word": "hello"}, {"word": "cat"}])
    try:
        done = load_existing(path)
        assert "hello" in done
        assert "cat" in done
    finally:
        os.unlink(path)


def test_load_existing_nonexistent_file():
    done = load_existing(Path("/tmp/definitely_does_not_exist_xyz.jsonl"))
    assert done == set()


def test_load_existing_empty_file():
    path = make_jsonl([])
    try:
        done = load_existing(path)
        assert done == set()
    finally:
        os.unlink(path)


def test_load_existing_skips_malformed_lines():
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    f.write('{"word": "hello"}\n')
    f.write("not valid json\n")
    f.write('{"word": "cat"}\n')
    f.close()
    try:
        done = load_existing(Path(f.name))
        assert "hello" in done
        assert "cat" in done
        assert len(done) == 2
    finally:
        os.unlink(f.name)


def test_load_existing_skips_entries_without_word_key():
    path = make_jsonl([{"translation": "ආයුබෝවන්"}, {"word": "cat"}])
    try:
        done = load_existing(path)
        assert done == {"cat"}
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# translate (mocked Ollama)
# ---------------------------------------------------------------------------


def mock_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"message": {"content": content}}
    return resp


def test_translate_returns_content():
    with patch("requests.post", return_value=mock_response("ආයුබෝවන්")):
        result = translate(
            "hello", "English (en)", "Sinhala (si)",
            "translategemma:4b", "http://localhost:11434/api/chat",
        )
    assert result == "ආයුබෝවන්"


def test_translate_strips_whitespace():
    with patch("requests.post", return_value=mock_response("  ආයුබෝවන්\n")):
        result = translate(
            "hello", "English (en)", "Sinhala (si)",
            "translategemma:4b", "http://localhost:11434/api/chat",
        )
    assert result == "ආයුබෝවන්"


def test_translate_sends_correct_model():
    with patch("requests.post", return_value=mock_response("x")) as mock_post:
        translate(
            "hello", "English (en)", "Sinhala (si)",
            "translategemma:4b", "http://localhost:11434/api/chat",
        )
    payload = mock_post.call_args[1]["json"]
    assert payload["model"] == "translategemma:4b"


def test_translate_sends_prompt_as_user_message():
    with patch("requests.post", return_value=mock_response("x")) as mock_post:
        translate(
            "hello", "English (en)", "Sinhala (si)",
            "translategemma:4b", "http://localhost:11434/api/chat",
        )
    messages = mock_post.call_args[1]["json"]["messages"]
    assert messages[0]["role"] == "user"
    assert "hello" in messages[0]["content"]


def test_translate_raises_on_http_error():
    resp = MagicMock()
    resp.raise_for_status.side_effect = Exception("HTTP 500")
    with patch("requests.post", return_value=resp):
        with pytest.raises(Exception, match="HTTP 500"):
            translate(
                "hello", "English (en)", "Sinhala (si)",
                "translategemma:4b", "http://localhost:11434/api/chat",
            )
