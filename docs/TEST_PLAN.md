# Test Plan — Provident Fund Demo API

## 1. Scope

| In scope | Out of scope |
|---|---|
| REST API functional behaviour (auth, members, contributions, balances, withdrawals) | Real payment rails, banking integration |
| Web UI critical journeys | Cross-browser matrix (Chromium only) |
| Security controls: authentication, lockout, audit trail, output escaping | Penetration testing, infrastructure hardening |
| ML risk-scoring model: quality, robustness, latency | Model training pipeline, data-drift monitoring |
| Load behaviour of the main endpoints against an SLA | Soak / stress-to-break testing |

## 2. Approach

| Level | Tool | Purpose |
|---|---|---|
| API functional + contract | pytest, requests, jsonschema | Business rules, negative paths, response schemas |
| API regression (manual & CI) | Postman + Newman | Collection usable by non-developers and runnable headless |
| UI end-to-end | Playwright (Page Object Model) | Critical user journeys; data seeded via API |
| ML model | pytest via API (black-box) | Quality gate, golden cases, metamorphic properties, latency |
| Performance | Locust | Mixed realistic workload with automatic SLA pass/fail |

**Test design techniques used**

- **Boundary-value analysis** — age 18 / 65 (± 1 day), amount 0.01 / 100,000 / 100,000.01
- **Equivalence partitioning** — ID and email formats, contributor types, period formats
- **Data-driven testing** — amount cases kept in `tests/data/contribution_amounts.json`
- **State-transition testing** — login → failed ×5 → locked; withdraw until balance exhausted
- **Metamorphic testing** — for the ML model, where the "correct" score is unknown, test relations
  that must hold (higher amount ⇒ score never lower)
- **Mutation check** — key tests are verified to *fail* when the protected behaviour is removed

## 3. Requirements traceability

| Rule | Requirement | Tests |
|---|---|---|
| R1 | Member ≥ 18 years old | `test_members.py::test_minimum_age_boundary` (6 cases), `test_under_age_member_is_rejected_in_ui`, Postman *Register under-age member* |
| R2 | Macao ID format `1234567(8)`, unique | `test_invalid_id_number_format_is_rejected` (8), `test_duplicate_id_number_is_rejected_with_409` |
| R3 | 0 < amount ≤ 100,000, ≤ 2 dp | `test_contribution_amount_boundaries` (10, data-driven), `test_amount_with_more_than_two_decimals_is_rejected` (**BUG-001**), UI `test_out_of_range_amount_shows_validation_message` |
| R4 | One contribution per member/period/type | `test_duplicate_contribution_same_period_and_type_returns_409`, `test_employee_and_employer_may_contribute_for_same_period`, UI `test_duplicate_contribution_shows_conflict_message` |
| R5 | Period not in the future, `YYYY-MM` | `test_contribution_period_validation` (9) |
| R6 | Withdraw only at 65+, within balance | `test_withdrawal_age_eligibility`, `test_withdraw_more_than_balance_is_rejected`, `test_successive_withdrawals_cannot_overdraw` |
| R7 | Lock after 5 failed logins | `test_account_locks_after_five_failed_attempts`, `test_successful_login_resets_failed_attempt_counter`, `test_lockout_is_per_user`, UI `test_lockout_message_after_five_failed_attempts` |
| R8 | Audit trail for security & financial events | `test_failed_and_successful_logins_are_audited`, `test_password_is_never_written_to_audit_log`, `test_contribution_is_audited`, `test_member_lifecycle_end_to_end` |
| SEC | Every business endpoint requires a valid token | `test_protected_endpoint_requires_token` (8 endpoints), `test_forged_token_is_rejected`, `test_logout_invalidates_token` |
| SEC | Stored data rendered safely (XSS) | `test_member_name_is_rendered_as_text_not_html` |
| ML-Q | Accuracy ≥ 0.95, precision ≥ 0.85, recall ≥ 0.95, F1 ≥ 0.90 | `test_model_meets_quality_thresholds_on_holdout_set` |
| ML-P | p95 scoring latency < 100 ms | `test_p95_scoring_latency_within_budget` |
| PERF | p95 < 200 ms, failures < 1 % under 30 users | `perf/locustfile.py` SLA gate |

## 4. Environments & data

- System under test starts automatically on a free port with `APP_ENV=test`; `/test/reset` wipes state
  **before every test**, so tests are independent and order-agnostic.
- Set `SUT_URL=https://...` to run the same suites against a deployed environment.
- All personal data is synthetic (`tests/helpers/data_factory.py`).

## 5. Entry / exit criteria

**Entry:** build installs cleanly; `/health` returns 200.

**Exit (release gate):** all smoke tests pass; no failed tests other than tracked `xfail` defects;
model quality gate met; load-test SLA met.

## 6. Defect management

Defects are written up in `docs/` (see [BUG-001](BUG-001.md)) and pinned by an
`xfail(strict=True)` test, so the suite stays green while the defect is open and turns red
the moment it is fixed without the tracking marker being removed.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Flaky UI tests from timing | Playwright auto-waiting `expect` assertions; no fixed sleeps |
| Tests depending on each other's data | Per-test state reset + unique data factories |
| Date-dependent rules (age, period) breaking over time | Dates computed relative to "today", Feb-29 handled |
| Model retraining silently degrading quality | Quality gate + golden cases run on every commit |
