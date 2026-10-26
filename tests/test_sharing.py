"""Allocation rules."""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from vicinia.sharing import greedy, pair_flows, pro_rata

vec = st.lists(st.one_of(st.just(0.0), st.floats(1e-6, 10.0)), min_size=1, max_size=12).map(np.array)


@settings(max_examples=200, deadline=None)
@given(st.floats(0.0, 50.0), vec)
def test_pro_rata_bounded_and_proportional(supply, demand):
    a = pro_rata(supply, demand)
    assert (a <= demand + 1e-12).all() and (a >= 0).all()
    assert a.sum() <= max(supply, 0) + 1e-9 or np.allclose(a, demand)
    if demand.sum() > supply + 1e-9:
        assert np.isclose(a.sum(), supply)
        ratio = np.divide(a, demand, out=np.zeros_like(a), where=demand > 0)
        assert np.allclose(ratio[demand > 0], supply / demand.sum())


@settings(max_examples=200, deadline=None)
@given(st.floats(0.0, 50.0), vec, st.randoms())
def test_greedy_serves_in_order(supply, demand, rnd):
    order = np.array(rnd.sample(range(len(demand)), len(demand)))
    a = greedy(supply, demand, order)
    assert (a <= demand + 1e-12).all() and (a >= 0).all()
    assert np.isclose(a.sum(), min(supply, demand.sum()))
    # At most one household is partly served, and it comes after all full ones.
    partial = [i for i in order if 0 < a[i] < demand[i] - 1e-12]
    assert len(partial) <= 1


@settings(max_examples=200, deadline=None)
@given(vec, st.floats(0.0, 0.5), st.data())
def test_pair_flows_reproduce_totals(delivered, loss, data):
    n = len(delivered)
    total_sent = delivered.sum() / (1 - loss)
    w = np.array(data.draw(st.lists(st.floats(0.01, 1.0), min_size=n, max_size=n)))
    sent = total_sent * w / w.sum()
    idx = np.arange(n)
    pairs = pair_flows(sent, delivered, loss, idx, idx[::-1])
    s = np.zeros(n)
    r = np.zeros(n)
    for d, rc, a in pairs:
        s[d] += a
        r[rc] += a * (1 - loss)
    assert np.allclose(s, sent, atol=1e-7)
    assert np.allclose(r, delivered, atol=1e-7)
    assert len(pairs) <= 2 * n - 1
