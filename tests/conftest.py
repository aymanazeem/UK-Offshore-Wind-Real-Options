"""Shared fixtures. Most checks are structural identities that hold at any path count, so the
fixtures use a small, fast simulation. The one headline-value test sets its own path count."""

from __future__ import annotations

import pytest

from src import lsm_engine as lsm

N_FAST = 4000


@pytest.fixture(scope="session")
def defer_sim():
    """(price with room to defer, generation), small and fast."""
    return lsm.simulate(n_paths=N_FAST, extra_price_years=4, seed=42)


@pytest.fixture(scope="session")
def base_sim():
    """(price over the build and operating years, generation over the operating years),
    base-case seeds."""
    return lsm.simulate(n_paths=N_FAST, seed=42)
