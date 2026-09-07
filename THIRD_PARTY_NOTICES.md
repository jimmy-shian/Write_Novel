# Third-Party Notices & Attribution

This project incorporates architectural concepts, user experience workflows, and design patterns inspired by open-source projects. Each reference is handled according to its specific license and isolation boundary.

---

## 1. AI-Novel-Writer (GPL-3.0) — Clean-Room Behavioral Reference Only

- **Repository**: https://github.com/EthanYoQ/AI-Novel-Writer
- **License**: GNU General Public License v3.0 (GPL-3.0)
- **Isolation Policy**:
  - **Zero Code Reuse**: In strict adherence to clean-room engineering principles, this project contains **no direct copying, translation, adaptation, or mechanical transformation** of GPL-licensed source code from AI-Novel-Writer.
  - **Behavioral & UX Reference**: The workflow concepts (Chapter Blueprint, Human-in-the-loop Proposal inbox, Side-by-side Diff revision, and Foreshadowing tracking) were analyzed at the functional requirement level and independently implemented from scratch with clean interfaces, distinct data models, and original source code.

---

## 2. Monogatari-Assistant-FE (Apache-2.0)

- **Repository**: https://github.com/Heyairu/Monogatari-Assistant-FE
- **License**: Apache License 2.0
- **Attribution**:
  - Contains architectural and UI organization concepts inspired by *Monogatari Assistant FE* by Heyairu.
  - Copyright (c) 2024 Heyairu. Licensed under the Apache License, Version 2.0.
  - No trademarks, logos, or branding of Monogatari Assistant are used in this product.

---

## 3. Graphiti (Apache-2.0)

- **Repository**: https://github.com/getzep/graphiti
- **License**: Apache License 2.0
- **Attribution**:
  - The Temporal Knowledge Graph concepts (Episodes, Entities, Temporal Facts with validity windows `valid_from` / `invalid_from`, Fact Invalidation, and Dynamic Temporal Context Slicing) are inspired by *Graphiti* by Zep Inc.
  - Copyright (c) Zep, Inc. Licensed under the Apache License, Version 2.0.
  - Our embedded engine is an independent Python SQLite/NetworkX implementation tailored for novel narrative continuity.
