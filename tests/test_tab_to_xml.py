import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from tab_to_xml import load_enriched, tab_to_xml

NS = {
    "d": "http://www.apple.com/DTDs/DictionaryService-1.0.rng",
    "x": "http://www.w3.org/1999/xhtml",
}


def make_tab_file(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".tab", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


def make_jsonl(records: list[dict]) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    f.close()
    return f.name


def parse(xml_str: str) -> ET.Element:
    body = re.sub(r"^<\?xml[^?]*\?>\n", "", xml_str)
    ET.register_namespace("", "http://www.w3.org/1999/xhtml")
    ET.register_namespace("d", "http://www.apple.com/DTDs/DictionaryService-1.0.rng")
    return ET.fromstring(body)


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------


def test_xml_declaration():
    tab = make_tab_file("hello\tworld\n")
    try:
        assert tab_to_xml(tab).startswith('<?xml version="1.0" encoding="UTF-8"?>')
    finally:
        os.unlink(tab)


def test_root_element():
    tab = make_tab_file("hello\tworld\n")
    try:
        assert "dictionary" in parse(tab_to_xml(tab)).tag
    finally:
        os.unlink(tab)


def test_valid_xml():
    tab = make_tab_file("hello\tworld\nfoo\tbar|baz\n")
    try:
        assert parse(tab_to_xml(tab)) is not None
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Entry content
# ---------------------------------------------------------------------------


def test_basic_entry_present():
    tab = make_tab_file("hello\tආයුබෝවන්\n")
    try:
        xml = tab_to_xml(tab)
        assert "hello" in xml and "ආයුබෝවන්" in xml
    finally:
        os.unlink(tab)


def test_entry_has_index_and_title():
    tab = make_tab_file("hello\tworld\n")
    try:
        xml = tab_to_xml(tab)
        assert 'd:title="hello"' in xml and 'd:value="hello"' in xml
    finally:
        os.unlink(tab)


def test_single_definition_uses_paragraph():
    tab = make_tab_file("word\tdefinition\n")
    try:
        xml = tab_to_xml(tab)
        assert "<p>definition</p>" in xml and "<ol>" not in xml
    finally:
        os.unlink(tab)


def test_multiple_definitions_use_ordered_list():
    tab = make_tab_file("a\tfirst|second|third\n")
    try:
        xml = tab_to_xml(tab)
        assert "<ol>" in xml
        assert "<li>first</li>" in xml and "<li>third</li>" in xml
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------


def test_ampersand_escaped():
    tab = make_tab_file("a&b\tdefinition\n")
    try:
        assert "a&amp;b" in tab_to_xml(tab)
    finally:
        os.unlink(tab)


def test_angle_brackets_escaped():
    tab = make_tab_file("word\t<em>test</em>\n")
    try:
        xml = tab_to_xml(tab)
        assert "&lt;em&gt;" in xml
    finally:
        os.unlink(tab)


def test_quotes_escaped_valid_xml():
    tab = make_tab_file('say "hi"\tdefinition\n')
    try:
        parse(tab_to_xml(tab))  # must not throw
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_empty_lines_skipped():
    tab = make_tab_file("word1\tdef1\n\nword2\tdef2\n")
    try:
        assert tab_to_xml(tab).count("<d:entry") == 2
    finally:
        os.unlink(tab)


def test_lines_without_tab_skipped():
    tab = make_tab_file("no_tab_here\nword\tdef\n")
    try:
        assert tab_to_xml(tab).count("<d:entry") == 1
    finally:
        os.unlink(tab)


def test_combining_char_headword_skipped():
    tab = make_tab_file("ාේමන්\tromans\ngood\tdef\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 1 and "ාේමන්" not in xml
    finally:
        os.unlink(tab)


def test_valid_sinhala_not_skipped():
    tab = make_tab_file("ගෙදර\thome\n")
    try:
        assert tab_to_xml(tab).count("<d:entry") == 1
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Entry IDs
# ---------------------------------------------------------------------------


def test_entry_ids_unique():
    tab = make_tab_file("word1\tdef1\nword2\tdef2\nword3\tdef3\n")
    try:
        ids = re.findall(r'id="(entry_\d+)"', tab_to_xml(tab))
        assert len(ids) == len(set(ids))
    finally:
        os.unlink(tab)


def test_entry_count_matches_input():
    lines = "\n".join(f"word{i}\tdef{i}" for i in range(20))
    tab = make_tab_file(lines + "\n")
    try:
        assert tab_to_xml(tab).count("<d:entry") == 20
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Unicode
# ---------------------------------------------------------------------------


def test_sinhala_characters_preserved():
    tab = make_tab_file("cat\tපූසා\n")
    try:
        xml = tab_to_xml(tab)
        assert "පූසා" in xml
        parse(xml)
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Simple enrichment (translation-only format)
# ---------------------------------------------------------------------------


def test_simple_enriched_pos_rendered():
    tab = make_tab_file("hello\tworld\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "greeting", "romanized": "Ayubowan", "alternatives": []}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="pos"' in xml and "greeting" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_simple_enriched_romanized_rendered():
    tab = make_tab_file("hello\tworld\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "", "romanized": "Ayubowan", "alternatives": []}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="romanized"' in xml and "Ayubowan" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_simple_enriched_alternatives_rendered():
    tab = make_tab_file("hello\tworld\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "", "romanized": "", "alternatives": ["හෙලෝ"]}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="alternatives"' in xml and "හෙලෝ" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_no_enriched_unchanged():
    tab = make_tab_file("hello\tworld\n")
    try:
        xml = tab_to_xml(tab, None)
        assert 'class="pos"' not in xml and 'class="romanized"' not in xml
    finally:
        os.unlink(tab)


def test_simple_enriched_only_matching_word():
    tab = make_tab_file("hello\tworld\ncat\tpet\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "x", "pos": "greeting", "romanized": "", "alternatives": []}])
    try:
        assert tab_to_xml(tab, jsonl).count('class="pos"') == 1
    finally:
        os.unlink(tab); os.unlink(jsonl)


# ---------------------------------------------------------------------------
# Rich enrichment (two-model format)
# ---------------------------------------------------------------------------

GOAT_RECORD = {
    "word": "goat",
    "existing": ["එළු"],
    "phonetic": "/ɡəʊt/",
    "forms": [
        {"type": "noun", "form": "goat"},
        {"type": "plural noun", "form": "goats"},
    ],
    "definitions": [
        {
            "pos": "noun",
            "sense": "a hardy domesticated ruminant mammal",
            "sense_translated": "දෘඩ ගෘහස්ථ රොමින්ත් ක්ෂිරපායී",
            "sub_senses": ["a wild mammal related to the goat"],
            "sub_senses_translated": ["එළුවාට සම්බන්ධ"],
            "register": None,
            "region": None,
            "synonyms": [],
        },
        {
            "pos": "noun",
            "sense": "a lecherous man",
            "sense_translated": "කාමුක පුරුෂයෙකු",
            "sub_senses": [],
            "sub_senses_translated": [],
            "register": "informal",
            "region": None,
            "synonyms": ["lecher", "libertine"],
        },
    ],
    "model": "translategemma:4b",
    "model_def": "gemma3:12b",
}


def test_rich_phonetic_rendered():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="phonetic"' in xml and "/ɡəʊt/" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_rich_forms_rendered():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="forms"' in xml and "plural noun" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_rich_definitions_rendered():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert "a hardy domesticated ruminant mammal" in xml
        assert "දෘඩ ගෘහස්ථ රොමින්ත් ක්ෂිරපායී" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_rich_register_rendered():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="label"' in xml and "informal" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_rich_synonyms_rendered():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="synonyms"' in xml and "lecher" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_rich_sub_senses_rendered():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert "a wild mammal related to the goat" in xml
        assert "එළුවාට සම්බන්ධ" in xml
    finally:
        os.unlink(tab); os.unlink(jsonl)


def test_rich_valid_xml():
    tab = make_tab_file("goat\tඑළු\n")
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        parse(tab_to_xml(tab, jsonl))  # must not throw
    finally:
        os.unlink(tab); os.unlink(jsonl)


# ---------------------------------------------------------------------------
# load_enriched
# ---------------------------------------------------------------------------


def test_load_enriched_returns_full_record():
    jsonl = make_jsonl([
        {"word": "hello", "translation": "ආයුබෝවන්", "pos": "greeting", "romanized": "Ayubowan", "alternatives": []},
    ])
    try:
        enriched = load_enriched(jsonl)
        assert enriched["hello"]["pos"] == "greeting"
    finally:
        os.unlink(jsonl)


def test_load_enriched_rich_format():
    jsonl = make_jsonl([GOAT_RECORD])
    try:
        enriched = load_enriched(jsonl)
        assert "definitions" in enriched["goat"]
        assert enriched["goat"]["phonetic"] == "/ɡəʊt/"
    finally:
        os.unlink(jsonl)
