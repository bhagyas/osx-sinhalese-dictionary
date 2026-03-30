SHELL = /bin/bash

# Directories
DICT_DIR    = dictionary
BUILD_DIR   = build
SCRIPTS_DIR = scripts

# Apple DDK tools (bundled)
BIN_DIR    = DictUnifier.app/Contents/Resources/bin
CSS        = DictUnifier.app/Contents/Resources/templates/Dictionary.css
PLIST_TMPL = DictUnifier.app/Contents/Resources/templates/DictInfo.plist

# Dictionary names
DICTS = english-sinhala sinhala-english

# Install location
DICT_INSTALL_DIR = $(HOME)/Library/Dictionaries

VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
RELEASE_NAME = sinhalese-dictionary-$(VERSION)
RELEASE_ZIP  = $(BUILD_DIR)/$(RELEASE_NAME).zip

.PHONY: all clean install release test $(DICTS)

all: $(DICTS)

## Build a specific dictionary by name (e.g. make english-sinhala)
$(DICTS): %: $(BUILD_DIR)/%.dictionary

## Convert .tab → Apple DDK XML (merges enriched JSONL if present)
$(BUILD_DIR)/%.xml: $(DICT_DIR)/%.tab | $(BUILD_DIR)
	python3 $(SCRIPTS_DIR)/tab_to_xml.py $< \
	  $(if $(wildcard $(DICT_DIR)/$*.enriched.jsonl),--enriched $(DICT_DIR)/$*.enriched.jsonl,) \
	  -o $@

## Generate a per-dictionary Info.plist from the template
$(BUILD_DIR)/%.plist: $(PLIST_TMPL) | $(BUILD_DIR)
	sed -e 's/\$$DICT_NAME/$*/g' -e 's/\$$DICT_ID/$*/g' $< > $@

## Compile XML + plist → .dictionary bundle
$(BUILD_DIR)/%.dictionary: $(BUILD_DIR)/%.xml $(BUILD_DIR)/%.plist
	DICT_DEV_KIT_OBJ_DIR=$(BUILD_DIR)/objects/$* \
	  $(BIN_DIR)/build_dict.sh \
	    "$*" \
	    "$(BUILD_DIR)/$*.xml" \
	    "$(CSS)" \
	    "$(BUILD_DIR)/$*.plist"
	mv $(BUILD_DIR)/objects/$*/$*.dictionary $@

$(BUILD_DIR):
	mkdir -p $@

## Install both dictionaries to ~/Library/Dictionaries/
install: all
	mkdir -p $(DICT_INSTALL_DIR)
	cp -r $(BUILD_DIR)/english-sinhala.dictionary $(DICT_INSTALL_DIR)/
	cp -r $(BUILD_DIR)/sinhala-english.dictionary $(DICT_INSTALL_DIR)/
	@echo ""
	@echo "Installed. Open Dictionary.app → Preferences and enable the dictionaries."

## Build a release zip: pre-built dictionaries + double-click installer
release: all
	rm -rf $(BUILD_DIR)/$(RELEASE_NAME)
	mkdir -p $(BUILD_DIR)/$(RELEASE_NAME)
	cp -r $(BUILD_DIR)/english-sinhala.dictionary $(BUILD_DIR)/$(RELEASE_NAME)/
	cp -r $(BUILD_DIR)/sinhala-english.dictionary $(BUILD_DIR)/$(RELEASE_NAME)/
	cp $(SCRIPTS_DIR)/install.command $(BUILD_DIR)/$(RELEASE_NAME)/
	chmod +x $(BUILD_DIR)/$(RELEASE_NAME)/install.command
	cd $(BUILD_DIR) && zip -r $(RELEASE_NAME).zip $(RELEASE_NAME)
	@echo ""
	@echo "Release zip: $(RELEASE_ZIP)"

TRANSLATION_MODEL  ?= translategemma:4b
DEFINITION_MODEL   ?= gemma3:12b
TRIAL_LIMIT        ?= 20
TRIAL_OUTPUT       ?= /tmp/enrich-trial.jsonl

.PHONY: enrich-en-si enrich-si-en enrich-trial enrich-trial-inspect

## Trial run: enrich first $(TRIAL_LIMIT) entries to /tmp/enrich-trial.jsonl
enrich-trial:
	@rm -f $(TRIAL_OUTPUT)
	python3 $(SCRIPTS_DIR)/enrich.py $(DICT_DIR)/english-sinhala.tab \
	  --source-lang "English (en)" --target-lang "Sinhala (si)" \
	  --model $(TRANSLATION_MODEL) \
	  --definition-model $(DEFINITION_MODEL) \
	  --output $(TRIAL_OUTPUT) \
	  --limit $(TRIAL_LIMIT)
	@echo ""
	@echo "Trial output: $(TRIAL_OUTPUT)"
	@echo "Run 'make enrich-trial-inspect' to pretty-print the results."

## Pretty-print the trial output
enrich-trial-inspect:
	@cat $(TRIAL_OUTPUT) | python3 -c \
	  "import sys,json; [print(json.dumps(json.loads(l), indent=2, ensure_ascii=False)) for l in sys.stdin if l.strip()]" | less

## Full enrichment: English definitions (gemma3) + Sinhala translations (translategemma)
enrich-en-si:
	python3 $(SCRIPTS_DIR)/enrich.py $(DICT_DIR)/english-sinhala.tab \
	  --source-lang "English (en)" --target-lang "Sinhala (si)" \
	  --model $(TRANSLATION_MODEL) \
	  --definition-model $(DEFINITION_MODEL) \
	  --output $(DICT_DIR)/english-sinhala.enriched.jsonl

## Translation-only enrichment for Sinhala→English (no definition generation)
enrich-si-en:
	python3 $(SCRIPTS_DIR)/enrich.py $(DICT_DIR)/sinhala-english.tab \
	  --source-lang "Sinhala (si)" --target-lang "English (en)" \
	  --model $(TRANSLATION_MODEL) \
	  --output $(DICT_DIR)/sinhala-english.enriched.jsonl

## Run tests
test:
	python3 -m pytest tests/ -v

clean:
	rm -rf $(BUILD_DIR)
