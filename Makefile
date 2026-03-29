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

## Convert .tab → Apple DDK XML
$(BUILD_DIR)/%.xml: $(DICT_DIR)/%.tab | $(BUILD_DIR)
	python3 $(SCRIPTS_DIR)/tab_to_xml.py $< -o $@

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

## Run tests
test:
	python3 -m pytest tests/ -v

clean:
	rm -rf $(BUILD_DIR)
