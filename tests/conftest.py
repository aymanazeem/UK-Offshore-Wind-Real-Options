"""Shared fixtures.

The structural identities under test, defer |Δ|=0 at zero deferral, the abandon spine
reconstruction and the no-arbitrage add-on, are exact at any path count, so the fixtures run
a small, fast simulation. The one headline-value test sets its own path count to match the
documented base case.
"""

from __future__ import annotations

import pytest

from src import lsm_engine

N_FAST = 4000  # identities are path-count-independent, keep the suite quick


@pytest.fixture(scope="session")
def defer_sim():
    """(price (n, life+d_max), gen (n, life)), enough price columns to defer."""
    return lsm_engine.simulate(n_paths=N_FAST, d_max=4, seed=42)


@pytest.fixture(scope="session")
def abandon_sim():
    """(price (n, life), gen (n, life)), operating-life window, base-case seeds."""
    return lsm_engine.simulate_abandon(n_paths=N_FAST, seed=42)
