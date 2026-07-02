# E2E Test Infra: Write_Novel Agent Refactoring

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + BVA + Pairwise + Workload Testing.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| F1 | Worldview & Settings | ORIGINAL_REQUEST §R3 | 6 | 5 | ✓ |
| F2 | Character Bible | ORIGINAL_REQUEST §R2 | 3 | 6 | ✓ |
| F3 | Volumes & Chapters Planning | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ |
| F4 | Global Foreshadowing Precomputation | ORIGINAL_REQUEST §R2 | 4 | 5 | ✓ |
| F5 | Volume Skeleton & Writing | ORIGINAL_REQUEST §R3 | 7 | 6 | ✓ |

## Test Architecture
- Test runner: `C:\Users\user\venv\Scripts\python.exe test_all.py`
- Test case format: standard Python unittest assertions (UTF-8 encoding)
- Directory layout: single test file `test_all.py` at project root

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Validation Report Walkthrough | F1, F2, F3, F4 | High |
| 2 | Initial Worldview Version Tracking | F1 | Low |
| 3 | Character Bible Evolution | F2 | Medium |
| 4 | Epic Skeleton Planning | F3 | Medium |
| 5 | Foreshadowing Update & Heal | F4 | Medium |
| 6 | Writing Preparation & Context Compaction | F5 | Medium |

## Coverage Thresholds
- Tier 1: ≥5 per feature (Total: 25)
- Tier 2: ≥5 per feature (Total: 27)
- Tier 3: pairwise coverage of major feature interactions (Total: 5)
- Tier 4: ≥5 realistic application scenarios (Total: 6)
- **Total: 63 test cases**
