#!/usr/bin/env python3
"""Convert a tab-separated dictionary file to Apple DDK XML format.

Tab file format:
    word<TAB>definition1|definition2|...

Output is Apple Dictionary Development Kit XML, suitable for passing
directly to build_dict.sh from the Dictionary Development Kit.

If an --enriched JSONL file is supplied (produced by enrich.py), each
entry is augmented with the LLM-generated translation shown as an
additional section in the definition body.
"""

import argparse
import html
import json
import sys
import unicodedata
from pathlib import Path


def load_enriched(jsonl_path: str) -> dict[str, str]:
    """Return {word: translation} from an enriched .jsonl file."""
    enriched: dict[str, str] = {}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("word") and rec.get("translation"):
                    enriched[rec["word"]] = rec["translation"]
            except (json.JSONDecodeError, KeyError):
                pass
    return enriched


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
            # Skip headwords starting with a combining character — they are
            # malformed (e.g. a Sinhala vowel sign with no base consonant) and
            # cause normalize_key_text to abort.
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
        if len(defs) == 1:
            parts.append(f"    <p>{html.escape(defs[0])}</p>")
        else:
            parts.append("    <ol>")
            for d in defs:
                parts.append(f"      <li>{html.escape(d)}</li>")
            parts.append("    </ol>")
        if word in enriched:
            parts.append(
                f'    <p class="enriched">{html.escape(enriched[word])}</p>'
            )
        parts.append("  </d:entry>")

    parts.append("</d:dictionary>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tab_file", help="Input .tab file")
    parser.add_argument("-o", "--output", help="Output XML file (default: stdout)")
    parser.add_argument(
        "--enriched",
        help="Optional enriched .jsonl file from enrich.py",
        default=None,
    )
    args = parser.parse_args()

    xml = tab_to_xml(args.tab_file, args.enriched)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(xml)
    else:
        sys.stdout.write(xml)


if __name__ == "__main__":
    main()
