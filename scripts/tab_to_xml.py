#!/usr/bin/env python3
"""Convert a tab-separated dictionary file to Apple DDK XML format.

Tab file format:
    word<TAB>definition1|definition2|...

Output is Apple Dictionary Development Kit XML, suitable for passing
directly to build_dict.sh from the Dictionary Development Kit.

If an --enriched JSONL file is supplied (produced by enrich.py), each
entry is augmented with LLM-generated content. Two record formats are
supported:

  Rich format (two-model pipeline, has "definitions" key):
    phonetic, grammatical forms, numbered definitions with pos/register/
    region/synonyms, and Sinhala translations of each sense.

  Simple format (translation-only, has "translation" key):
    primary translation, romanized pronunciation, part of speech,
    and alternative translations.
"""

import argparse
import html
import json
import sys
import unicodedata
from pathlib import Path


def load_enriched(jsonl_path: str) -> dict[str, dict]:
    """Return {word: record} from an enriched .jsonl file."""
    enriched: dict[str, dict] = {}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("word"):
                    enriched[rec["word"]] = rec
            except (json.JSONDecodeError, KeyError):
                pass
    return enriched


def render_rich(rec: dict) -> list[str]:
    """Render a full definition record (two-model pipeline output)."""
    parts = []

    if rec.get("phonetic"):
        parts.append(f'    <p class="phonetic">{html.escape(rec["phonetic"])}</p>')

    if rec.get("forms"):
        forms_str = "; ".join(
            f'{html.escape(f["type"])}: {html.escape(f["form"])}'
            for f in rec["forms"] if f.get("type") and f.get("form")
        )
        if forms_str:
            parts.append(f'    <p class="forms">{forms_str}</p>')

    definitions = rec.get("definitions", [])
    if definitions:
        parts.append("    <ol>")
        for d in definitions:
            parts.append("      <li>")
            if d.get("pos"):
                parts.append(f'        <span class="pos">{html.escape(d["pos"])}</span>')
            if d.get("register") or d.get("region"):
                labels = " · ".join(
                    html.escape(x) for x in [d.get("register"), d.get("region")] if x
                )
                parts.append(f'        <span class="label">{labels}</span>')
            if d.get("sense"):
                parts.append(f'        <span class="sense">{html.escape(d["sense"])}</span>')
            if d.get("sense_translated"):
                parts.append(f'        <span class="sense-si">{html.escape(d["sense_translated"])}</span>')
            if d.get("sub_senses"):
                parts.append('        <ul class="sub-senses">')
                for j, sub in enumerate(d["sub_senses"]):
                    parts.append(f"          <li>{html.escape(sub)}")
                    translated = (d.get("sub_senses_translated") or [])
                    if j < len(translated) and translated[j]:
                        parts.append(f'            <span class="sense-si">{html.escape(translated[j])}</span>')
                    parts.append("          </li>")
                parts.append("        </ul>")
            if d.get("synonyms"):
                syns = ", ".join(html.escape(s) for s in d["synonyms"])
                parts.append(f'        <p class="synonyms">{syns}</p>')
            parts.append("      </li>")
        parts.append("    </ol>")

    return parts


def render_simple(rec: dict) -> list[str]:
    """Render a simple (translation-only) enrichment record."""
    parts = []
    if rec.get("pos"):
        parts.append(f'    <p class="pos"><em>{html.escape(rec["pos"])}</em></p>')
    if rec.get("romanized"):
        parts.append(f'    <p class="romanized">/{html.escape(rec["romanized"])}/</p>')
    if rec.get("alternatives"):
        alts = ", ".join(html.escape(a) for a in rec["alternatives"])
        parts.append(f'    <p class="alternatives">{alts}</p>')
    return parts


def tab_to_xml(tab_file: str, enriched_file: str | None = None) -> str:
    enriched = load_enriched(enriched_file) if enriched_file else {}

    entries = []
    with open(tab_file, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            word, _, definitions = line.partition("\t")
            word = word.strip()
            defs = [d.strip() for d in definitions.split("|") if d.strip()]
            if not word or not defs:
                continue
            # Skip headwords starting with a combining character — malformed data
            if unicodedata.category(word[0]) in ("Mn", "Mc", "Me"):
                continue
            entries.append((i, word, defs))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<d:dictionary xmlns="http://www.w3.org/1999/xhtml"'
        ' xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">',
    ]

    for entry_id, word, defs in entries:
        ew = html.escape(word)
        parts.append(f'  <d:entry id="entry_{entry_id}" d:title="{ew}">')
        parts.append(f'    <d:index d:value="{ew}"/>')
        parts.append(f"    <h1>{ew}</h1>")

        # Base definitions from .tab file
        if len(defs) == 1:
            parts.append(f"    <p>{html.escape(defs[0])}</p>")
        else:
            parts.append("    <ol>")
            for d in defs:
                parts.append(f"      <li>{html.escape(d)}</li>")
            parts.append("    </ol>")

        # Enriched content (if available)
        if word in enriched:
            rec = enriched[word]
            if "definitions" in rec:
                parts.extend(render_rich(rec))
            else:
                parts.extend(render_simple(rec))

        parts.append("  </d:entry>")

    parts.append("</d:dictionary>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tab_file", help="Input .tab file")
    parser.add_argument("-o", "--output", help="Output XML file (default: stdout)")
    parser.add_argument("--enriched", help="Optional enriched .jsonl from enrich.py", default=None)
    args = parser.parse_args()

    xml = tab_to_xml(args.tab_file, args.enriched)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(xml)
    else:
        sys.stdout.write(xml)


if __name__ == "__main__":
    main()
