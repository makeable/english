# English Structure Highlighter

Syntax highlighting for English prose. The text is parsed with [spaCy](https://spacy.io) and coloured by its grammar:

- **Parts of speech:** nouns, verbs, adjectives, adverbs and the rest
- **Sentence roles:** subject, predicate, object, complement, adjunct (the head word is shown in bold)
- **Clauses:** relative, adverbial and complement clauses get a tint, darker the deeper they are nested
- **Named entities:** people, places, organisations, dates, quantities
- **Style hints:** passive voice, long sentences, filler words and repeated words, shown as diagnostics
- **Hover:** any word shows its tag, grammar features, lemma, dependency and role

It works on `.txt` and `.md` files. Markdown code blocks, inline code, link URLs and front matter are skipped.

## How it's built

```
server/          Python language server (pygls + spaCy). Any LSP editor can use it.
client/vscode/   VS Code extension: starts the server, switches views, draws clause/entity decorations
samples/         Demo document
```

Analysis runs in **layers** (`server/src/english_ls/layers/`). To add deeper analysis, such as phrase trees, coreference or semantic roles, write a new layer and add it to `default_layers()` in `analyzer.py`.

## Setup

Requires Python 3.10–3.13, [uv](https://docs.astral.sh/uv/) and Node 18+.

```bash
cd server && uv sync
```

This installs the small model (`en_core_web_sm`). For the most accurate parse, install the transformer model. It pulls in PyTorch, which is roughly a 1 GB download:

```bash
cd server && uv sync --extra trf
```

`--extra lg` gives a good middle ground without PyTorch. The server uses the model set in `english.model`, and falls back to whichever English model is installed.

```bash
cd client/vscode && npm install && npm run compile
```

## Run it in VS Code

Open `client/vscode` in VS Code and press **F5**. A new window opens with `samples/` loaded.

When the extension runs from this repo, it finds `server/.venv` by itself. Anywhere else, set `english.pythonPath` to a Python that has `english-ls` installed.

- **English: Switch Highlight View** (or click the status bar item) switches between *All*, *Parts of speech*, *Sentence roles* and *Entities*.
- **English: Apply Recommended Colours** adds a palette that reads well on light and dark themes. Without it, colours come from your theme's code colours.

## Other editors

The server speaks standard LSP (semantic tokens, hover, diagnostics), so any LSP editor can use it. For example, in Neovim:

```lua
vim.lsp.start({ name = "english", cmd = { "/path/to/server/.venv/bin/python", "-m", "english_ls" } })
```

## Tests

```bash
cd server && uv run pytest
```

```bash
cd client/vscode && npm test
```

The VS Code test uses your installed VS Code if it finds one. It runs in a temporary profile with other extensions turned off, and the window closes when the test ends.
