# CLI and Configuration Architecture

## What this shows

The command surface of the application and how user-facing commands relate to configuration resolution and interactive setup tooling. It groups commands by concern (core conversion, guided setup, custom endpoint management, generic config editing, cache maintenance, authentication, usage reporting, logs, diagnostics) and shows how the interactive tools funnel into one typed settings model that ultimately reads from and writes to the local configuration database — plus how the core conversion command feeds the live dashboard.

## Key design decisions

The command surface is organized around distinct operator concerns rather than one flat command list: processing commands, setup/configuration commands, and inspection commands (stats, history, logs, doctor) are separated so each stays focused. Configuration resolution follows a strict, layered precedence — explicit command-line flags beat saved configuration, which beats environment variables, which beat built-in defaults — and that precedence is applied through one typed settings model rather than being re-implemented per command. Interactive tooling (the setup wizard, the config editor, the custom endpoint manager) all exist as guided front-ends onto that same settings model and the same configuration database, rather than as separate configuration stores — so a setting changed through the wizard is immediately visible to `config get` and vice versa. The live dashboard is deliberately fed by the processing command's event stream rather than embedded inside the pipeline itself, keeping "how progress is displayed" separate from "how work happens."

## Tradeoffs

Funneling every configuration path through one typed settings model adds a small amount of indirection for simple single-value changes, but it guarantees that validation, precedence, and persistence behave identically whether a setting was touched by a wizard, an editor, or a raw `config set`. Separating inspection commands (stats, history, doctor) from the mutating ones keeps each command simple, at the cost of a slightly larger overall command surface for a user to learn. Keeping the dashboard decoupled from the pipeline via events makes the UI layer swappable and testable independently, but means every pipeline stage that should be visible to the user must remember to emit an event rather than the UI simply observing internal state directly.
