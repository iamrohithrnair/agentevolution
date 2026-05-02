"""Self-evolution demo for Dronan.

Three modules:

- :mod:`dronan.demo.scenario` — the canonical *Airport Corridor Storm* scenario,
  encoded as a deterministic dataclass (locations, supplies, priorities, storm
  trigger time, obstacle injection time). No LLM nondeterminism in the inputs.
- :mod:`dronan.demo.runner` — invokes the scenario N times against a clean
  ``missions`` slate while preserving ``mission_memory`` across takes; writes
  per-take aggregates to ``experiments``. Provides a deterministic
  :class:`~dronan.demo.runner.SimulatedSupervisor` for offline tests +
  rehearsals; production uses Session A's ``dronan.graph.build_supervisor``.
- :mod:`dronan.demo.charts` — produces a server-side SVG of ``actual_time_s``
  per take. No Recharts on the server (we mirror the client's chart in §11.3
  of ``prompts/10`` but keep it pure-Python so the FastAPI ``/analytics``
  endpoint can render it without a JS dep).

Phase 7 of ``prompts/13-implementation-plan.md``. Acceptance tests AT-7.1
(``test_self_evolution.py``) and AT-7.2 (``test_memory_recall.py``) live in
``backend/tests``.
"""

from dronan.demo import charts, runner, scenario

__all__ = ["charts", "runner", "scenario"]
