# Alfred Project – Developer Instructions for Copilot

## 1. Project Overview

Alfred is a modular personal AI assistant built with Python and Streamlit.

The project follows a brick-based architecture:
each brick (module) is responsible for a single functional domain
(email, memory, routing, interpretation, etc.).

Core objectives:
- stability over novelty
- maintainability over clever abstractions
- predictable behavior between local and online environments

Alfred is developed with a “stable core + minimal patches” philosophy.

---

## 2. High-Level Architecture

Main entry point:
- alfred.py → Streamlit UI and orchestration only

Routing and interpretation:
- router.py → routes user intents to the appropriate brick
- interpreteur.py → translates natural language intent into actions

Core bricks:
- gestionemails.py → email logic (intents, flows, persistence)
- memoire_alfred.py → long-term memory handling
- llm.py → LLM access and model selection
- lecturefichiersbase.py → file reading utilities
- connexiongoogle*.py / connexionmail.py → external service connectors

Extensible bricks:
- skills/ → optional and future modular skills

---

## 3. Dependency Rules (IMPORTANT)

Bricks may depend on other bricks, but only under strict conditions:

- Dependencies must be explicit and visible through imports
- No hidden or implicit coupling
- Prefer one-directional dependencies
- Avoid circular imports
- Shared logic should be extracted into a clearly identified helper module
  rather than ad-hoc cross-imports

Each brick should remain understandable and testable in isolation.

---

## 4. Development Rules for Copilot

When modifying the code:

- Do not refactor large portions unless explicitly requested
- Prefer minimal, isolated, and reversible patches
- Do not change public behavior without explanation
- Do not introduce new dependencies lightly
- Never break local behavior to fix online behavior (or the opposite)
- If local and online behavior differ, explain the cause before proposing a fix

---

## 5. Local vs Online Constraints

The project may behave differently in local and online environments.

Known constraints:
- environment variables may differ
- file system access may be restricted online
- authentication and permissions may vary

Any proposed change must explicitly state whether it affects:
- local execution
- online execution
- or both

---

## 6. Adding New Bricks or Skills

New features should preferably be implemented as:

- a new standalone brick (new Python file), or
- a new module inside the skills/ directory

Each new brick must:
- have a single, clear responsibility
- expose a clean and documented entry point
- avoid tight coupling with existing bricks

Copilot should propose:
- the new file
- how it integrates with the existing architecture
- without modifying unrelated bricks

---

## 7. Expected Workflow

For bugs or evolutions:

1. Identify the concerned brick(s)
2. Provide a diagnosis
3. Propose a minimal patch
4. Let the user review
5. Test locally
6. Commit and push
7. Test online

---

## 8. Philosophy Reminder

Stability > Cleverness  
Explicit > Implicit  
Small patches > Large refactors

If something is unclear, Copilot must ask before acting.
