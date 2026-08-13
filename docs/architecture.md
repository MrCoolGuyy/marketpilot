# MarketPilot — Architecture

## Overview

MarketPilot follows **Clean Architecture** principles with clear layer separation and dependency inversion.  High-level business logic depends on abstractions (interfaces), not on concrete implementations.

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / Streamlit                       │
├──────────┬──────────┬──────────┬──────────┬─────────────────┤
│  Scanner │  (Future │  (Future │  (Future │                 │
│          │ Strategy)│ Executor)│   Risk)  │                 │
├──────────┴──────────┴──────────┴──────────┤    Utils        │
│                  Models                    │  (logging,      │
├────────────────────────────────────────────┤   decorators,   │
│              Config / Settings             │   helpers)      │
├────────────────────────────────────────────┤                 │
│            Core (interfaces, enums,        │                 │
│            exceptions, constants)          │                 │
├────────────────────────────────────────────┴─────────────────┤
│                        Storage                               │
│              (SQLAlchemy, Repository)                         │
└─────────────────────────────────────────────────────────────┘
```

## Dependency Flow

```
CLI → Config → Core (interfaces)
         ↕
      Models ← Core (enums)
         ↕
     Storage → Core (interfaces, exceptions)
         ↕
      Utils  → Config (settings)
```

**Key rules:**

1. **Core** has zero internal dependencies — it defines contracts only
2. **Models** depend only on Core enums
3. **Config** depends on Core constants
4. **Storage** implements Core interfaces
5. **Utils** are cross-cutting but never depend on Storage or Scanner
6. **Scanner** (future) will implement `BaseScanner` from Core

## SOLID Principles Applied

| Principle | Application |
|-----------|-------------|
| **S**ingle Responsibility | Each module has one reason to change (e.g. `exceptions.py` only defines errors) |
| **O**pen/Closed | New asset types → add enum value, no existing code changes |
| **L**iskov Substitution | Any `BaseExchangeClient` subclass is interchangeable |
| **I**nterface Segregation | `BaseScanner`, `BaseStorage`, `BaseExchangeClient` are separate interfaces |
| **D**ependency Inversion | High-level modules depend on ABCs, not concrete classes |
