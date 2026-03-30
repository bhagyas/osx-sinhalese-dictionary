#!/usr/bin/env python3
"""Enrich dictionary tab files using a local translategemma model via Ollama.

Reads a .tab file and for each entry calls translategemma to produce a
structured enrichment record containing:
  - translation:   primary translation in the target language
  - alternatives:  additional synonyms (deduplicated, garbage-filtered)
  - romanized:     romanized pronunciation of the primary translation
  - pos:           part of speech (noun, verb, adjective, etc.)

Results are appended to a .jsonl file so the run is fully resumable —
stop and restart at any time without losing progress.

The enriched .jsonl is committed to the repo as a permanent artefact.
tab_to_xml.py merges it into the XML output automatically if present.

Examples:

  # Enrich English → Sinhala (run once, takes a while for 49k entries)
  python3 scripts/enrich.py dictionary/english-sinhala.tab \\
      --source-lang "English (en)" --target-lang "Sinhala (si)" \\
      --output dictionary/english-sinhala.enriched.jsonl

  # Improve Sinhala → English (the auto-generated reverse file)
  python3 scripts/enrich.py dictionary/sinhala-english.tab \\
      --source-lang "Sinhala (si)" --target-lang "English (en)" \\
      --output dictionary/sinhala-english.enriched.jsonl

  # Quick smoke-test (first 10 entries only)
  python3 scripts/enrich.py dictionary/english-sinhala.tab \\
      --source-lang "English (en)" --target-lang "Sinhala (si)" \\
      --output /tmp/test.jsonl --limit 10
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "translategemma:4b"


def make_prompt(word: str, source_lang: str, target_lang: str) -> str:
    return (
        f"You are a professional {source_lang} to {target_lang} translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original "
        f"{source_lang} text while adhering to {target_lang} grammar, vocabulary, "
        f"and cultural sensitivities.\n\n"
        f"For the {source_lang} word below, provide the following in JSON format "
        f"only, no commentary:\n"
        f'- "translation": the primary {target_lang} translation\n'
        f'- "alternatives": up to 3 alternative {target_lang} translations or synonyms\n'
        f'- "romanized": romanized pronunciation of the primary translation\n'
        f'- "pos": part of speech (noun, verb, adjective, adverb, etc.)\n\n'
        f"{source_lang} word: {word}"
    )


def is_clean(text: str) -> bool:
    """Return False if text looks like garbage (e.g. Latin mixed into Sinhala)."""
    # Allow pure ASCII (for en→si reverse entries) or pure Sinhala Unicode block
    # Reject strings that mix Sinhala script with non-ASCII Latin characters
    has_sinhala = bool(re.search(r"[\u0D80-\u0DFF]", text))
    has_latin_extended = bool(re.search(r"[À-ÿ]", text))
    return not (has_sinhala and has_latin_extended)


def parse_response(raw: str, primary: str) -> dict:
    """Parse the JSON blob from the model, with graceful fallback."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"translation": primary, "alternatives": [], "romanized": "", "pos": ""}

    translation = str(data.get("translation", primary)).strip() or primary
    romanized = str(data.get("romanized", "")).strip()
    pos = str(data.get("pos", "")).strip()

    # Deduplicate and filter garbage from alternatives
    seen = {translation}
    alternatives = []
    for alt in data.get("alternatives", []):
        alt = str(alt).strip()
        if alt and alt not in seen and is_clean(alt):
            alternatives.append(alt)
            seen.add(alt)

    return {
        "translation": translation,
        "alternatives": alternatives,
        "romanized": romanized,
        "pos": pos,
    }


def translate(
    word: str,
    source_lang: str,
    target_lang: str,
    model: str,
    ollama_url: str,
) -> dict:
    prompt = make_prompt(word, source_lang, target_lang)
    resp = requests.post(
        ollama_url,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"].strip()
    return parse_response(raw, word)


def load_tab(tab_path: str) -> list[tuple[str, list[str]]]:
    entries = []
    with open(tab_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or "\t" not in line:
                continue
            word, _, defs = line.partition("\t")
            word = word.strip()
            existing = [d.strip() for d in defs.split("|") if d.strip()]
            if word and existing:
                entries.append((word, existing))
    return entries


def load_existing(jsonl_path: Path) -> set[str]:
    """Return set of words already present in the output JSONL."""
    done: set[str] = set()
    if not jsonl_path.exists():
        return done
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["word"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def enrich(
    tab_file: str,
    output: str,
    source_lang: str,
    target_lang: str,
    model: str,
    ollama_url: str,
    limit: int = 0,
) -> None:
    entries = load_tab(tab_file)
    out_path = Path(output)
    done = load_existing(out_path)

    pending = [(w, e) for w, e in entries if w not in done]
    if limit:
        pending = pending[:limit]

    total = len(pending)
    print(
        f"Entries to enrich: {total}  (skipping {len(done)} already done)",
        flush=True,
    )

    if not total:
        print("Nothing to do.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    with open(out_path, "a", encoding="utf-8") as f:
        for i, (word, existing) in enumerate(pending, 1):
            try:
                enriched = translate(word, source_lang, target_lang, model, ollama_url)
                record = {
                    "word": word,
                    "existing": existing,
                    **enriched,
                    "model": model,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                print(
                    f"[{i}/{total}] {word} → {enriched['translation']}"
                    + (f"  [{enriched['pos']}]" if enriched["pos"] else "")
                    + (f"  /{enriched['romanized']}/" if enriched["romanized"] else ""),
                    flush=True,
                )
            except Exception as e:
                errors += 1
                print(f"[{i}/{total}] ERROR {word}: {e}", file=sys.stderr, flush=True)

    if errors:
        print(f"\nFinished with {errors} error(s). Re-run to retry failed entries.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("tab_file", help="Input .tab file")
    parser.add_argument("--output", "-o", required=True, help="Output .jsonl file")
    parser.add_argument(
        "--source-lang", default="English (en)", help='e.g. "English (en)"'
    )
    parser.add_argument(
        "--target-lang", default="Sinhala (si)", help='e.g. "Sinhala (si)"'
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help="Ollama API base URL")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only N entries (0 = all); useful for testing",
    )
    args = parser.parse_args()

    enrich(
        args.tab_file,
        args.output,
        args.source_lang,
        args.target_lang,
        args.model,
        args.ollama_url,
        args.limit,
    )


if __name__ == "__main__":
    main()
