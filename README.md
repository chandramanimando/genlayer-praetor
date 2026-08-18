# Praetor — Two-Instance AI Adjudication Primitive for GenLayer

Praetor is a reusable intelligent-contract primitive: a **court-as-oracle**.
Other contracts query it to resolve subjective conditions — Was the deliverable
accepted? Was the SLA breached? Did the insured event occur? — instead of each
contract re-implementing ad-hoc "AI decides X" logic.

## Why it is not a demo

| Rubric requirement | How Praetor answers it |
|---|---|
| Real consensus logic | State is designed for GenLayer's optimistic democracy: only **normalized verdict enums + bucketed confidence** are stored, never raw model text, so validator re-executions converge. |
| Thoughtful equivalence | Custom `@contract.equivalence` over decision-critical state; normalization makes exact equality achievable. |
| Clear state design | Explicit machine: `FIRST_INSTANCE → (appeal \| finalize) → FINAL`. |
| Meaningful use case | Adjudication oracle for escrows, insurance, SLAs — any contract needing subjective truth. |

## Architecture
