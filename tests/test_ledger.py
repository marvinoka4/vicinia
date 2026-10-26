"""Settlement ledger: hash chain, tamper detection, netting."""

import dataclasses

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vicinia.ledger import Ledger

entry = st.tuples(
    st.integers(0, 500),
    st.integers(0, 9),
    st.integers(0, 9),
    st.floats(0.0, 5.0),
    st.floats(0.0, 0.5),
).filter(lambda e: e[1] != e[2])


def build(entries, price=400.0):
    led = Ledger(price)
    for t, s, r, kwh, loss in entries:
        led.append(t, s, r, kwh, kwh * (1 - loss))
    return led


@settings(max_examples=100, deadline=None)
@given(st.lists(entry, min_size=1, max_size=40))
def test_chain_verifies_and_nets_to_zero(entries):
    led = build(entries)
    assert led.verify()
    assert led.first_invalid() is None
    periods = np.arange(501) // 96
    net = led.netting(10, periods)
    assert net.groupby("period")["net_kobo"].sum().eq(0).all()
    st_ = led.statements(10)
    assert st_["ngn_net"].sum() == pytest.approx(0, abs=1e-9)
    assert st_["kwh_sold"].sum() >= st_["kwh_bought"].sum() - 1e-12


@settings(max_examples=100, deadline=None)
@given(
    st.lists(entry, min_size=1, max_size=40),
    st.data(),
)
def test_any_altered_entry_fails_verification(entries, data):
    led = build(entries)
    i = data.draw(st.integers(0, len(led.entries) - 1))
    field = data.draw(st.sampled_from(["interval", "sender", "receiver", "kwh_sent", "kwh_received", "price_ngn_per_kwh", "amount_kobo"]))
    e = led.entries[i]
    old = getattr(e, field)
    new = old + 1 if isinstance(old, int) else old + 0.001
    led.entries[i] = dataclasses.replace(e, **{field: new})
    assert not led.verify()
    assert led.first_invalid() == i


def test_deleting_or_reordering_entries_fails():
    led = build([(0, 0, 1, 1.0, 0.05), (1, 1, 2, 2.0, 0.05), (2, 2, 0, 3.0, 0.05)])
    led2 = build([(0, 0, 1, 1.0, 0.05), (1, 1, 2, 2.0, 0.05), (2, 2, 0, 3.0, 0.05)])
    del led.entries[1]
    del led.hashes[1]
    assert not led.verify()
    led2.entries[0], led2.entries[1] = led2.entries[1], led2.entries[0]
    assert not led2.verify()


def test_rejects_invalid_entries():
    led = Ledger(400.0)
    with pytest.raises(ValueError):
        led.append(0, 1, 1, 1.0, 1.0)
    with pytest.raises(ValueError):
        led.append(0, 1, 2, 1.0, 1.5)
    with pytest.raises(ValueError):
        led.append(0, 1, 2, -1.0, 0.0)


def test_buyer_pays_for_delivered_energy():
    led = Ledger(400.0)
    e = led.append(3, 0, 1, 1.0, 0.95)
    assert e.amount_kobo == 38000
    s = led.statements(2)
    assert s.loc[0, "ngn_earned"] == 380.0 and s.loc[1, "ngn_paid"] == 380.0
