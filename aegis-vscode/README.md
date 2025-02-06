# Aegis

<p align="center">
    A language server for projects using the <a href="https://github.com/mcbeet">Beet Ecosystem</a>    
</p>

> [!Warning]
> This extenstion is still a large work in progress! 
> Please report any issues to the [issue tracker](https://github.com/TheNuclearNexus/mecha-language-server/issues)!

## General Features
- Inline Diagnostics
- Code Completions
- Go-to Definition
- Hover hints
    - Nested and Relative Location resolution
    - Variable type hints
- Fully extensible by Beet plugins
    - Mileage may very outside of official plugins

## Configuration
Basic configuration can be done at the project level via your beet config.
```yml

# Pipeline plugins will be pulled automatically
# Mecha will always be added if not defined in order
# to provide diagnostics about files.
pipeline:
    - a
# Require plugins will be added automatically but 
# will only have their *first* step down (everything before the first `yield`)
# this is to minimize side-effects created by plugins 
# after files have been loaded. If you want to modify syntax or parsing
# ensure setup is done in the first step of the plugin.
require:
    - b

meta:
    lsp:
        # Accepts a list of plugins to *not* be loaded by the language server
        excluded_plugins: 
            - foo
```
