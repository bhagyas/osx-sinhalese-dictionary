osx-sinhalese-dictionary
========================

English to Sinhalese Dictionary for macOS (Mavericks through Sonoma, including Apple Silicon).

### Requirements

- macOS
- Python 3
- Apple's **Dictionary Development Kit** — install via Xcode → Settings → Components → **Xcode Additional Tools** (look for "Dictionary Development Kit" in the DMG)

> **Note:** The repo also bundles `DictUnifier.app` as a fallback for users who prefer a GUI. The `make` workflow does not require it.

---

### Build and install (recommended)

```sh
git clone https://github.com/bhagyas/osx-sinhalese-dictionary.git
cd osx-sinhalese-dictionary

make install
```

This builds both the English→Sinhala and Sinhala→English dictionaries and copies them to `~/Library/Dictionaries/`.

Open **Dictionary.app → Preferences** and check the box next to each dictionary to enable them.

#### Individual targets

| Command | Description |
|---|---|
| `make` | Build both dictionaries into `build/` |
| `make english-sinhala` | Build English→Sinhala only |
| `make sinhala-english` | Build Sinhala→English only |
| `make install` | Build and install to `~/Library/Dictionaries/` |
| `make test` | Run the test suite |
| `make clean` | Remove the `build/` directory |

---

### Install via DictUnifier (GUI alternative)

1. Open `DictUnifier.app`
2. Drag `dictionary/english-sinhala.ifo` onto the window
3. Press **Start** when prompted for a dictionary name
4. Open Dictionary.app → Preferences and enable **english-sinhala**

**Tip:** If you have more than 5 dictionaries, drag-and-drop their order in Dictionary Preferences to bring this one within the pop-up tooltip range.

---

### Screenshots

#### Dictionary tooltip (three-finger tap on trackpad)
![](https://raw.githubusercontent.com/bhagyas/osx-sinhalese-dictionary/images/dictionary-images/dictionary-tooltip.png)

#### Manual lookup
![](https://raw.githubusercontent.com/bhagyas/osx-sinhalese-dictionary/images/dictionary-images/dictionary-example.png)

#### Enable dictionary
![](https://raw.githubusercontent.com/bhagyas/osx-sinhalese-dictionary/images/dictionary-images/dictionary-enable.png)

---

### How it works

```
dictionary/*.tab  (tab-separated source data, ~49k entries each direction)
      |
      v
scripts/tab_to_xml.py  (Python — converts to Apple DDK XML)
      |
      v
Apple DDK build_dict.sh  (compiles XML into binary .dictionary bundle)
      |
      v
~/Library/Dictionaries/*.dictionary
      |
      v
macOS Dictionary.app
```

The `.tab` files are the canonical source of truth. `scripts/tab_to_xml.py` replaces the old `sdconv` binary (x86_64-only, Python 2.7 dependency) and works natively on both Intel and Apple Silicon Macs.

---

### Development

Run the test suite:

```sh
make test
```

To regenerate the Sinhala→English tab file from the English→Sinhala source:

```sh
perl dictionary/si_en.pl > dictionary/sinhala-english.tab
```

---

### Credits

- Language Technology Research Laboratory, University of Colombo
- Buddhika Siddhisena
- Bhagya Nirmaan Silva

### Author

Bhagya Nirmaan Silva (http://www.about.me/bhagyas)

Made with love in Sweden. <3
