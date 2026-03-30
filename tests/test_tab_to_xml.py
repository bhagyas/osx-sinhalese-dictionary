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
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".tab", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


def parse(xml_str: str) -> ET.Element:
    # Strip the XML declaration so ElementTree can parse it
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
        xml = tab_to_xml(tab)
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    finally:
        os.unlink(tab)


def test_root_element():
    tab = make_tab_file("hello\tworld\n")
    try:
        root = parse(tab_to_xml(tab))
        assert "dictionary" in root.tag
    finally:
        os.unlink(tab)


def test_valid_xml():
    tab = make_tab_file("hello\tworld\nfoo\tbar|baz\n")
    try:
        root = parse(tab_to_xml(tab))
        assert root is not None
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Entry content
# ---------------------------------------------------------------------------


def test_basic_entry_present():
    tab = make_tab_file("hello\tආයුබෝවන්\n")
    try:
        xml = tab_to_xml(tab)
        assert "hello" in xml
        assert "ආයුබෝවන්" in xml
    finally:
        os.unlink(tab)


def test_entry_has_index_and_title():
    tab = make_tab_file("hello\tworld\n")
    try:
        xml = tab_to_xml(tab)
        assert 'd:title="hello"' in xml
        assert 'd:value="hello"' in xml
    finally:
        os.unlink(tab)


def test_single_definition_uses_paragraph():
    tab = make_tab_file("word\tdefinition\n")
    try:
        xml = tab_to_xml(tab)
        assert "<p>definition</p>" in xml
        assert "<ol>" not in xml
    finally:
        os.unlink(tab)


def test_multiple_definitions_use_ordered_list():
    tab = make_tab_file("a\tfirst|second|third\n")
    try:
        xml = tab_to_xml(tab)
        assert "<ol>" in xml
        assert "<li>first</li>" in xml
        assert "<li>second</li>" in xml
        assert "<li>third</li>" in xml
    finally:
        os.unlink(tab)


def test_two_definitions_use_list():
    tab = make_tab_file("word\tone|two\n")
    try:
        xml = tab_to_xml(tab)
        assert "<ol>" in xml
        assert "<li>one</li>" in xml
        assert "<li>two</li>" in xml
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------


def test_ampersand_escaped_in_word():
    tab = make_tab_file("a&b\tdefinition\n")
    try:
        xml = tab_to_xml(tab)
        assert "a&amp;b" in xml
        assert "a&b" not in xml.split("?>", 1)[1]  # not in body
    finally:
        os.unlink(tab)


def test_angle_brackets_escaped_in_definition():
    tab = make_tab_file("word\t<em>test</em>\n")
    try:
        xml = tab_to_xml(tab)
        assert "&lt;em&gt;" in xml
        assert "<em>" not in xml.split("dictionary>", 1)[1]
    finally:
        os.unlink(tab)


def test_quotes_escaped_in_word():
    tab = make_tab_file('say "hi"\tdefinition\n')
    try:
        xml = tab_to_xml(tab)
        assert "&quot;" in xml or "&#34;" in xml or "say " in xml
        # The title attribute must be valid XML — parse confirms this
        parse(xml)
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Skipping / filtering
# ---------------------------------------------------------------------------


def test_empty_lines_skipped():
    tab = make_tab_file("word1\tdef1\n\nword2\tdef2\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 2
    finally:
        os.unlink(tab)


def test_lines_without_tab_skipped():
    tab = make_tab_file("no_tab_here\nword\tdef\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 1
    finally:
        os.unlink(tab)


def test_pipe_only_definition_skipped():
    tab = make_tab_file("word\t|||\ngood\tdef\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 1
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Entry IDs
# ---------------------------------------------------------------------------


def test_entry_ids_are_unique():
    tab = make_tab_file("word1\tdef1\nword2\tdef2\nword3\tdef3\n")
    try:
        xml = tab_to_xml(tab)
        ids = re.findall(r'id="(entry_\d+)"', xml)
        assert len(ids) == len(set(ids))
    finally:
        os.unlink(tab)


def test_entry_count_matches_input():
    lines = "\n".join(f"word{i}\tdef{i}" for i in range(20))
    tab = make_tab_file(lines + "\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 20
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Unicode / Sinhala
# ---------------------------------------------------------------------------


def test_sinhala_characters_preserved():
    tab = make_tab_file("cat\tපූසා\n")
    try:
        xml = tab_to_xml(tab)
        assert "පූසා" in xml
        parse(xml)  # must still be valid XML
    finally:
        os.unlink(tab)


def test_sinhala_headword():
    tab = make_tab_file("ගෙදර\thome|house\n")
    try:
        xml = tab_to_xml(tab)
        assert "ගෙදර" in xml
        assert "<li>home</li>" in xml
        assert "<li>house</li>" in xml
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Combining character filtering
# ---------------------------------------------------------------------------


def test_combining_char_headword_skipped():
    # U+0DCF SINHALA VOWEL SIGN AELA-PILLA starts with Mc category — invalid headword
    tab = make_tab_file("ාේමන්\tromans\ngood\tdef\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 1
        assert "ාේමන්" not in xml
    finally:
        os.unlink(tab)


def test_combining_char_al_lakuna_skipped():
    # U+0DCA SINHALA SIGN AL-LAKUNA is Mn category
    tab = make_tab_file("්ෙබියානුවාදය\ttest\ngood\tdef\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 1
    finally:
        os.unlink(tab)


def test_valid_sinhala_not_skipped():
    # Starts with a normal Sinhala consonant — must not be filtered
    tab = make_tab_file("ගෙදර\thome\n")
    try:
        xml = tab_to_xml(tab)
        assert xml.count("<d:entry") == 1
    finally:
        os.unlink(tab)


# ---------------------------------------------------------------------------
# Enriched JSONL merging
# ---------------------------------------------------------------------------


def make_jsonl(records: list[dict]) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    f.close()
    return f.name


def test_enriched_pos_rendered():
    tab = make_tab_file("hello\tworld\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "greeting", "romanized": "Ayubowan", "alternatives": []}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="pos"' in xml
        assert "greeting" in xml
    finally:
        os.unlink(tab)
        os.unlink(jsonl)


def test_enriched_romanized_rendered():
    tab = make_tab_file("hello\tworld\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "", "romanized": "Ayubowan", "alternatives": []}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="romanized"' in xml
        assert "Ayubowan" in xml
    finally:
        os.unlink(tab)
        os.unlink(jsonl)


def test_enriched_alternatives_rendered():
    tab = make_tab_file("hello\tworld\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "", "romanized": "", "alternatives": ["හෙලෝ"]}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert 'class="alternatives"' in xml
        assert "හෙලෝ" in xml
    finally:
        os.unlink(tab)
        os.unlink(jsonl)


def test_no_enriched_file_unchanged():
    tab = make_tab_file("hello\tworld\n")
    try:
        xml = tab_to_xml(tab, None)
        assert 'class="pos"' not in xml
        assert 'class="romanized"' not in xml
    finally:
        os.unlink(tab)


def test_enriched_only_for_matching_word():
    tab = make_tab_file("hello\tworld\ncat\tpet\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "ආයුබෝවන්", "pos": "greeting", "romanized": "", "alternatives": []}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert xml.count('class="pos"') == 1
    finally:
        os.unlink(tab)
        os.unlink(jsonl)


def test_load_enriched_returns_dict():
    jsonl = make_jsonl([
        {"word": "hello", "translation": "ආයුබෝවන්", "pos": "greeting", "romanized": "Ayubowan", "alternatives": []},
        {"word": "cat", "translation": "පූසා", "pos": "noun", "romanized": "Pusa", "alternatives": []},
    ])
    try:
        enriched = load_enriched(jsonl)
        assert enriched["hello"]["translation"] == "ආයුබෝවන්"
        assert enriched["hello"]["pos"] == "greeting"
        assert enriched["cat"]["translation"] == "පූසා"
    finally:
        os.unlink(jsonl)


def test_enriched_html_escaped():
    tab = make_tab_file("hello\tdef\n")
    jsonl = make_jsonl([{"word": "hello", "translation": "x", "pos": "<script>", "romanized": "", "alternatives": []}])
    try:
        xml = tab_to_xml(tab, jsonl)
        assert "&lt;script&gt;" in xml
        assert "<script>" not in xml.split("?>", 1)[1]
        parse(xml)
    finally:
        os.unlink(tab)
        os.unlink(jsonl)
