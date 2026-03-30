import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from enrich import (
    is_clean,
    load_existing,
    load_tab,
    make_definition_prompt,
    make_simple_prompt,
    make_translation_prompt,
    parse_definition_response,
    parse_simple_response,
    strip_fences,
)


# ---------------------------------------------------------------------------
# make_definition_prompt
# ---------------------------------------------------------------------------


def test_definition_prompt_contains_word():
    prompt = make_definition_prompt("goat")
    assert prompt.endswith("goat")


def test_definition_prompt_requests_json_fields():
    prompt = make_definition_prompt("goat")
    for field in ("phonetic", "forms", "definitions", "pos", "sense", "synonyms"):
        assert field in prompt


def test_definition_prompt_requests_json_only():
    prompt = make_definition_prompt("goat")
    assert "JSON" in prompt and "no commentary" in prompt


# ---------------------------------------------------------------------------
# make_translation_prompt
# ---------------------------------------------------------------------------


def test_translation_prompt_contains_text():
    prompt = make_translation_prompt("a hardy mammal", "English (en)", "Sinhala (si)")
    assert "a hardy mammal" in prompt


def test_translation_prompt_contains_languages():
    prompt = make_translation_prompt("text", "English (en)", "Sinhala (si)")
    assert "English (en)" in prompt
    assert "Sinhala (si)" in prompt


# ---------------------------------------------------------------------------
# make_simple_prompt
# ---------------------------------------------------------------------------


def test_simple_prompt_ends_with_word():
    prompt = make_simple_prompt("cat", "English (en)", "Sinhala (si)")
    assert prompt.endswith("cat")


def test_simple_prompt_requests_all_fields():
    prompt = make_simple_prompt("cat", "English (en)", "Sinhala (si)")
    for field in ("translation", "alternatives", "romanized", "pos"):
        assert field in prompt


# ---------------------------------------------------------------------------
# strip_fences
# ---------------------------------------------------------------------------


def test_strip_fences_removes_json_fence():
    assert strip_fences("```json\n{}\n```") == "{}"


def test_strip_fences_removes_plain_fence():
    assert strip_fences("```\n{}\n```") == "{}"


def test_strip_fences_passthrough_no_fence():
    assert strip_fences('{"a": 1}') == '{"a": 1}'


# ---------------------------------------------------------------------------
# is_clean
# ---------------------------------------------------------------------------


def test_clean_sinhala_only():
    assert is_clean("ආයුබෝවන්") is True


def test_clean_ascii_only():
    assert is_clean("hello") is True


def test_dirty_sinhala_mixed_with_latin_extended():
    assert is_clean("සුභවාünsche") is False


def test_clean_sinhala_with_punctuation():
    assert is_clean("ආයුබෝවන්!") is True


# ---------------------------------------------------------------------------
# parse_definition_response
# ---------------------------------------------------------------------------


GOAT_RESPONSE = {
    "phonetic": "/ɡəʊt/",
    "forms": [
        {"type": "noun", "form": "goat"},
        {"type": "plural noun", "form": "goats"},
    ],
    "definitions": [
        {
            "pos": "noun",
            "sense": "a hardy domesticated ruminant mammal",
            "sub_senses": ["a wild mammal related to the goat"],
            "register": None,
            "region": None,
            "synonyms": [],
        },
        {
            "pos": "noun",
            "sense": "a lecherous man",
            "sub_senses": [],
            "register": "informal",
            "region": None,
            "synonyms": ["lecher", "libertine"],
        },
    ],
}


def test_parse_definition_response_phonetic():
    result = parse_definition_response(json.dumps(GOAT_RESPONSE))
    assert result["phonetic"] == "/ɡəʊt/"


def test_parse_definition_response_forms():
    result = parse_definition_response(json.dumps(GOAT_RESPONSE))
    assert result["forms"][0] == {"type": "noun", "form": "goat"}
    assert result["forms"][1]["type"] == "plural noun"


def test_parse_definition_response_definitions():
    result = parse_definition_response(json.dumps(GOAT_RESPONSE))
    assert len(result["definitions"]) == 2
    assert result["definitions"][0]["sense"] == "a hardy domesticated ruminant mammal"
    assert result["definitions"][0]["sub_senses"] == ["a wild mammal related to the goat"]


def test_parse_definition_response_register():
    result = parse_definition_response(json.dumps(GOAT_RESPONSE))
    assert result["definitions"][1]["register"] == "informal"
    assert result["definitions"][0]["register"] is None


def test_parse_definition_response_synonyms():
    result = parse_definition_response(json.dumps(GOAT_RESPONSE))
    assert result["definitions"][1]["synonyms"] == ["lecher", "libertine"]


def test_parse_definition_response_strips_markdown():
    raw = "```json\n" + json.dumps(GOAT_RESPONSE) + "\n```"
    result = parse_definition_response(raw)
    assert result is not None
    assert result["phonetic"] == "/ɡəʊt/"


def test_parse_definition_response_returns_none_on_bad_json():
    assert parse_definition_response("not json") is None


# ---------------------------------------------------------------------------
# parse_simple_response
# ---------------------------------------------------------------------------


def test_parse_simple_response_basic():
    raw = json.dumps({
        "translation": "ආයුබෝවන්",
        "alternatives": ["හෙලෝ"],
        "romanized": "Ayubowan",
        "pos": "greeting",
    })
    result = parse_simple_response(raw, "hello")
    assert result["translation"] == "ආයුබෝවන්"
    assert result["romanized"] == "Ayubowan"
    assert result["pos"] == "greeting"


def test_parse_simple_response_deduplicates_alternatives():
    raw = json.dumps({
        "translation": "ආයුබෝවන්",
        "alternatives": ["ආයුබෝවන්", "ආයුබෝවන්", "හෙලෝ"],
        "romanized": "",
        "pos": "",
    })
    result = parse_simple_response(raw, "hello")
    assert result["alternatives"] == ["හෙලෝ"]


def test_parse_simple_response_filters_garbage():
    raw = json.dumps({
        "translation": "ආයුබෝවන්",
        "alternatives": ["සුභවාünsche", "හෙලෝ"],
        "romanized": "",
        "pos": "",
    })
    result = parse_simple_response(raw, "hello")
    assert "සුභවාünsche" not in result["alternatives"]
    assert "හෙලෝ" in result["alternatives"]


def test_parse_simple_response_fallback_on_bad_json():
    result = parse_simple_response("not valid json", "hello")
    assert result["translation"] == "hello"
    assert result["alternatives"] == []


# ---------------------------------------------------------------------------
# load_tab
# ---------------------------------------------------------------------------


def make_tab(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".tab", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def test_load_tab_basic():
    path = make_tab("hello\tworld\n")
    try:
        assert load_tab(path) == [("hello", ["world"])]
    finally:
        os.unlink(path)


def test_load_tab_multiple_definitions():
    path = make_tab("a\tone|two|three\n")
    try:
        assert load_tab(path) == [("a", ["one", "two", "three"])]
    finally:
        os.unlink(path)


def test_load_tab_skips_empty_lines():
    path = make_tab("hello\tworld\n\nfoo\tbar\n")
    try:
        assert len(load_tab(path)) == 2
    finally:
        os.unlink(path)


def test_load_tab_skips_lines_without_tab():
    path = make_tab("notabhere\nhello\tworld\n")
    try:
        assert len(load_tab(path)) == 1
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# load_existing
# ---------------------------------------------------------------------------


def make_jsonl(lines: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    for line in lines:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    f.close()
    return Path(f.name)


def test_load_existing_returns_words():
    path = make_jsonl([{"word": "hello"}, {"word": "cat"}])
    try:
        done = load_existing(path)
        assert "hello" in done and "cat" in done
    finally:
        os.unlink(path)


def test_load_existing_nonexistent_file():
    assert load_existing(Path("/tmp/does_not_exist_xyz.jsonl")) == set()


def test_load_existing_skips_malformed_lines():
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    f.write('{"word": "hello"}\nnot json\n{"word": "cat"}\n')
    f.close()
    try:
        done = load_existing(Path(f.name))
        assert done == {"hello", "cat"}
    finally:
        os.unlink(f.name)
