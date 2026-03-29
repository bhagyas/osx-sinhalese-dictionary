#!/usr/bin/env python3
"""Convert a tab-separated dictionary file to Apple DDK XML format.

Tab file format:
    word<TAB>definition1|definition2|...

Output is Apple Dictionary Development Kit XML, suitable for passing
directly to build_dict.sh from the Dictionary Development Kit.
"""

import argparse
import html
import sys


def tab_to_xml(tab_file: str) -> str:
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
        parts.append("  </d:entry>")

    parts.append("</d:dictionary>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tab_file", help="Input .tab file")
    parser.add_argument("-o", "--output", help="Output XML file (default: stdout)")
    args = parser.parse_args()

    xml = tab_to_xml(args.tab_file)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(xml)
    else:
        sys.stdout.write(xml)


if __name__ == "__main__":
    main()
