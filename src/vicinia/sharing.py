"""Allocation rules used by the sharing strategies.

Amounts are energy per interval in kWh. Receiver demands and allocations are
in delivered (after loss) units; donor offers and contributions are in sent
units. With loss fraction L, delivering r kWh requires r / (1 - L) kWh sent.
"""

from __future__ import annotations

import numpy as np

EPS = 1e-12


def pro_rata(supply: float, demand: np.ndarray) -> np.ndarray:
    """Serve all demand if possible, otherwise scale every demand equally."""
    total = float(demand.sum())
    if total <= supply + EPS:
        return demand.copy()
    if total <= 0:
        return np.zeros_like(demand)
    return demand * (supply / total)


def greedy(supply: float, demand: np.ndarray, order: np.ndarray) -> np.ndarray:
    """Serve demands in full, one by one in `order`, until supply runs out."""
    alloc = np.zeros_like(demand)
    left = supply
    for r in order:
        if left <= EPS:
            break
        d = demand[r]
        if d <= 0:
            continue
        a = d if d < left else left
        alloc[r] = a
        left -= a
    return alloc


def pair_flows(
    sent: np.ndarray,
    delivered: np.ndarray,
    loss: float,
    donor_order: np.ndarray,
    receiver_order: np.ndarray,
) -> list[tuple[int, int, float]]:
    """Decompose aggregate donor and receiver totals into pairwise transfers.

    Uses a north-west-corner walk: donors in `donor_order` fill receivers in
    `receiver_order`. Produces at most (donors + receivers - 1) pairs, each
    (sender, receiver, kwh_sent). Totals per donor and per receiver match the
    inputs to floating point precision.
    """
    keep = 1.0 - loss
    donors = [int(d) for d in donor_order if sent[d] > EPS]
    recvs = [int(r) for r in receiver_order if delivered[r] > EPS]
    pairs: list[tuple[int, int, float]] = []
    i = j = 0
    d_left = sent[donors[0]] if donors else 0.0
    r_left = delivered[recvs[0]] / keep if recvs else 0.0
    while i < len(donors) and j < len(recvs):
        a = min(d_left, r_left)
        if a > EPS:
            pairs.append((donors[i], recvs[j], a))
        d_left -= a
        r_left -= a
        if d_left <= EPS:
            i += 1
            if i < len(donors):
                d_left = sent[donors[i]]
        if r_left <= EPS:
            j += 1
            if j < len(recvs):
                r_left = delivered[recvs[j]] / keep
    return pairs


def contributions(total_sent: float, offers: np.ndarray, order: np.ndarray | None) -> np.ndarray:
    """Split a total sent amount across donors: pro-rata, or in `order` if given."""
    if order is None:
        return pro_rata(total_sent, offers)
    return greedy(total_sent, offers, order)
