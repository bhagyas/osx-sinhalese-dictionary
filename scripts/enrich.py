#!/usr/bin/env python3
"""Enrich dictionary tab files using local LLMs via Ollama.

Two-model pipeline:
  1. Definition model (e.g. gemma3:12b) — generates a full English
     dictionary entry: IPA, grammatical forms, numbered definitions,
     sub-senses, register/region labels, synonyms.
  2. Translation model (e.g. translategemma:4b) — translates each
     definition sense into the target language.

If --definition-model is omitted, only the translation step runs
(original single-model behaviour, useful for SI→EN).

Results are appended to a .jsonl file — fully resumable at any time.
The enriched .jsonl is committed to the repo as a permanent artefact;
tab_to_xml.py merges it into the XML output automatically if present.

Examples:

  # Full pipeline: English definitions + Sinhala translations
  python3 scripts/enrich.py dictionary/english-sinhala.tab \\
      --source-lang "English (en)" --target-lang "Sinhala (si)" \\
      --definition-model gemma3:12b \\
      --output dictionary/english-sinhala.enriched.jsonl

  # Translation only (SI→EN, no definition generation)
  python3 scripts/enrich.py dictionary/sinhala-english.tab \\
      --source-lang "Sinhala (si)" --target-lang "English (en)" \\
      --output dictionary/sinhala-english.enriched.jsonl

  # Quick smoke-test (first 5 entries)
  python3 scripts/enrich.py dictionary/english-sinhala.tab \\
      --source-lang "English (en)" --target-lang "Sinhala (si)" \\
      --definition-model gemma3:12b \\
      --output /tmp/test.jsonl --limit 5
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
DEFAULT_DEFINITION_MODEL = "gemma3:12b"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def make_definition_prompt(word: str) -> str:
    return (
        "You are a professional lexicographer. "
        "For the English word below, produce a complete dictionary entry "
        "as JSON only, no commentary, using exactly this structure:\n\n"
        "{\n"
        '  "phonetic": "IPA string e.g. /ɡəʊt/",\n'
        '  "forms": [\n'
        '    {"type": "noun", "form": "goat"},\n'
        '    {"type": "plural noun", "form": "goats"}\n'
        "  ],\n"
        '  "definitions": [\n'
        "    {\n"
        '      "pos": "noun",\n'
        '      "sense": "primary definition text",\n'
        '      "sub_senses": ["additional related sense"],\n'
        '      "register": "informal or derogatory or null",\n'
        '      "region": "US English or British English or null",\n'
        '      "synonyms": ["synonym1", "synonym2"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Word: {word}"
    )


def make_translation_prompt(text: str, source_lang: str, target_lang: str) -> str:
    return (
        f"You are a professional {source_lang} to {target_lang} translator. "
        f"Your goal is to accurately convey the meaning and nuances of the original "
        f"{source_lang} text while adhering to {target_lang} grammar, vocabulary, "
        f"and cultural sensitivities.\n"
        f"Produce only the {target_lang} translation, without any additional "
        f"explanations or commentary. "
        f"Please translate the following {source_lang} text into {target_lang}:\n\n\n"
        f"{text}"
    )


def make_simple_prompt(word: str, source_lang: str, target_lang: str) -> str:
    """Used when no definition model is configured (translation-only mode)."""
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


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def call_ollama(prompt: str, model: str, ollama_url: str) -> str:
    resp = requests.post(
        ollama_url,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def strip_fences(raw: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)


def is_clean(text: str) -> bool:
    """Return False if text mixes Sinhala script with extended Latin (garbage)."""
    has_sinhala = bool(re.search(r"[\u0D80-\u0DFF]", text))
    has_latin_extended = bool(re.search(r"[À-ÿ]", text))
    return not (has_sinhala and has_latin_extended)


def parse_definition_response(raw: str) -> dict | None:
    """Parse the definition JSON from the definition model. Returns None on failure."""
    try:
        data = json.loads(strip_fences(raw))
    except json.JSONDecodeError:
        return None

    definitions = []
    for d in data.get("definitions", []):
        definitions.append({
            "pos": str(d.get("pos", "")).strip(),
            "sense": str(d.get("sense", "")).strip(),
            "sub_senses": [str(s).strip() for s in d.get("sub_senses", []) if s],
            "register": str(d.get("register", "") or "").strip() or None,
            "region": str(d.get("region", "") or "").strip() or None,
            "synonyms": [str(s).strip() for s in d.get("synonyms", []) if s],
        })

    return {
        "phonetic": str(data.get("phonetic", "")).strip(),
        "forms": [
            {"type": str(f.get("type", "")), "form": str(f.get("form", ""))}
            for f in data.get("forms", [])
        ],
        "definitions": definitions,
    }


def parse_simple_response(raw: str, fallback_word: str) -> dict:
    """Parse the simple (translation-only) JSON response."""
    try:
        data = json.loads(strip_fences(raw))
    except json.JSONDecodeError:
        return {"translation": fallback_word, "alternatives": [], "romanized": "", "pos": ""}

    translation = str(data.get("translation", fallback_word)).strip() or fallback_word
    romanized = str(data.get("romanized", "")).strip()
    pos = str(data.get("pos", "")).strip()

    seen = {translation}
    alternatives = []
    for alt in data.get("alternatives", []):
        alt = str(alt).strip()
        if alt and alt not in seen and is_clean(alt):
            alternatives.append(alt)
            seen.add(alt)

    return {"translation": translation, "alternatives": alternatives, "romanized": romanized, "pos": pos}


# ---------------------------------------------------------------------------
# Core enrichment
# ---------------------------------------------------------------------------


def translate_text(text: str, source_lang: str, target_lang: str, model: str, ollama_url: str) -> str:
    prompt = make_translation_prompt(text, source_lang, target_lang)
    return call_ollama(prompt, model, ollama_url).strip()


def enrich_word_full(
    word: str,
    source_lang: str,
    target_lang: str,
    definition_model: str,
    translation_model: str,
    ollama_url: str,
) -> dict:
    """Run the two-model pipeline: generate definition then translate each sense."""
    # Step 1: generate English definition
    def_raw = call_ollama(make_definition_prompt(word), definition_model, ollama_url)
    definition = parse_definition_response(def_raw)

    if definition is None:
        # Definition model failed — fall back to simple translation
        simple_raw = call_ollama(make_simple_prompt(word, source_lang, target_lang), translation_model, ollama_url)
        return parse_simple_response(simple_raw, word)

    # Step 2: translate each sense with the translation model
    for d in definition["definitions"]:
        if d["sense"]:
            d["sense_translated"] = translate_text(d["sense"], source_lang, target_lang, translation_model, ollama_url)
        d["sub_senses_translated"] = [
            translate_text(s, source_lang, target_lang, translation_model, ollama_url)
            for s in d["sub_senses"]
        ]

    return definition


def enrich_word_simple(
    word: str,
    source_lang: str,
    target_lang: str,
    translation_model: str,
    ollama_url: str,
) -> dict:
    """Translation-only mode (no definition model)."""
    raw = call_ollama(make_simple_prompt(word, source_lang, target_lang), translation_model, ollama_url)
    return parse_simple_response(raw, word)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Main enrichment loop
# ---------------------------------------------------------------------------


def enrich(
    tab_file: str,
    output: str,
    source_lang: str,
    target_lang: str,
    model: str,
    definition_model: str | None,
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
    mode = f"definition({definition_model}) + translation({model})" if definition_model else f"translation({model})"
    print(f"Mode: {mode}", flush=True)
    print(f"Entries to enrich: {total}  (skipping {len(done)} already done)", flush=True)

    if not total:
        print("Nothing to do.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    errors = 0
    with open(out_path, "a", encoding="utf-8") as f:
        for i, (word, existing) in enumerate(pending, 1):
            try:
                if definition_model:
                    enriched = enrich_word_full(word, source_lang, target_lang, definition_model, model, ollama_url)
                else:
                    enriched = enrich_word_simple(word, source_lang, target_lang, model, ollama_url)

                record = {
                    "word": word,
                    "existing": existing,
                    **enriched,
                    "model": model,
                    **({"model_def": definition_model} if definition_model else {}),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()

                # Progress summary
                if "definitions" in enriched:
                    first_sense = enriched["definitions"][0].get("sense", "") if enriched["definitions"] else ""
                    print(f"[{i}/{total}] {word} — {first_sense[:60]}{'…' if len(first_sense) > 60 else ''}", flush=True)
                else:
                    print(f"[{i}/{total}] {word} → {enriched.get('translation', '?')}", flush=True)

            except Exception as e:
                errors += 1
                print(f"[{i}/{total}] ERROR {word}: {e}", file=sys.stderr, flush=True)

    if errors:
        print(f"\nFinished with {errors} error(s). Re-run to retry failed entries.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("tab_file", help="Input .tab file")
    parser.add_argument("--output", "-o", required=True, help="Output .jsonl file")
    parser.add_argument("--source-lang", default="English (en)")
    parser.add_argument("--target-lang", default="Sinhala (si)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Translation model (translategemma:4b)")
    parser.add_argument(
        "--definition-model",
        default=None,
        help="Definition model (e.g. gemma3:12b). If omitted, translation-only mode.",
    )
    parser.add_argument("--ollama-url", default=OLLAMA_URL)
    parser.add_argument("--limit", type=int, default=0, help="Process only N entries (0 = all)")
    args = parser.parse_args()

    enrich(
        args.tab_file, args.output,
        args.source_lang, args.target_lang,
        args.model, args.definition_model,
        args.ollama_url, args.limit,
    )


if __name__ == "__main__":
    main()
