# 📦 Dependency Detective

**Smart. Automatic. Zero-hassle Python dependency management.**

Dependency Detective is a powerful, modern command-line tool that **automatically discovers**, **resolves**, **installs**, and **manages** the third-party dependencies your Python project actually uses — **without you ever having to manually maintain a `requirements.txt` file again**.

It scans your codebase using proper **AST parsing** (not brittle regex), intelligently maps top-level imports to real PyPI package names (even for tricky ones like `cv2` → `opencv-python`, `bs4` → `beautifulsoup4`, `PIL` → `Pillow`, etc.), excludes standard library & local modules, queries PyPI for latest versions when needed, and gives you multiple powerful workflows:

- Generate clean, version-pinned `requirements.txt`
- Auto-install missing packages into your current environment
- Create a fresh `./venv` with only the dependencies your project needs
- Run your code in an **isolated temporary virtual environment** (great for demos, CI checks, one-off scripts)
- Dry-run mode to preview changes
- Beautiful rich-formatted output

Perfect for solo developers, open-source maintainers, students, data scientists, and anyone tired of broken "works on my machine" moments.

## ✨ Highlights

- **Accurate import detection** via Python's built-in `ast` module (handles `import X`, `from X import Y`, aliases, etc.)
- **Smart package name resolution** with a large built-in mapping table + custom mappings via CLI
- **Ignores** stdlib, local project modules/packages, `__pycache__`, `venv`, `dist`, etc.
- **Supports** `pyproject.toml` configuration (`[tool.depdetective]`)
- **Can fetch latest versions** from PyPI when generating pinned requirements
- **Rich console output** using [rich](https://github.com/Textualize/rich) — colorful, clean, modern
- **Multiple execution modes** — generate files, install deps, create venv, temp-run, dry-run
- **Self-aware** — never scans itself during analysis

## Comparison – Why Dependency Detective?

| Feature                              | pipreqs          | pip-compile / poetry | pipdeptree       | Dependency Detective          |
|--------------------------------------|------------------|-----------------------|------------------|-------------------------------|
| AST-based import detection           | No (regex)       | No                    | No               | **Yes**                       |
| Smart import → package mapping       | Basic            | Manual                | No               | **Extensive + customizable**  |
| Auto-install missing packages        | No               | No                    | No               | **Yes**                       |
| Create isolated `./venv`             | No               | Partial               | No               | **Yes** (persistent)          |
| Run in temporary throwaway venv      | No               | No                    | No               | **Yes**                       |
| Generate pinned `requirements.txt`   | Yes (unpinned)   | Yes                   | No               | **Yes** (tries to pin)        |
| pyproject.toml config support        | No               | Yes (poetry)          | No               | **Yes**                       |
| Beautiful modern console UI          | No               | No                    | Basic tree       | **Yes (rich)**                |
| Dry-run / preview mode               | No               | Partial               | No               | **Yes**                       |

If you want something **smarter than pipreqs** and **lighter than Poetry/Pipenv**, Dependency Detective is for you.

## Installation

### Recommended: install globally or in user space
```bash
pip install requests rich rich-argparse tomli
```
### Then just copy or symlink the script:
```bash
#   cp dependency_detective.py ~/bin/depdet
# or
#   ln -s $(pwd)/dependency_detective.py ~/bin/depdet
```
