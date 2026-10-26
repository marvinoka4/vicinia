"""Hash-chained settlement ledger.

Every energy transfer between two households is one entry. Each entry's hash
is SHA-256 over the previous entry's hash and the entry's canonical text, so
changing, inserting or deleting any entry breaks verification from that point
onwards.

Money is held in integer kobo (1 NGN = 100 kobo) so that payments net to
exactly zero. The buyer pays for energy received; distribution losses are
therefore borne by the seller, who is paid for what arrives.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

GENESIS = "0" * 64


@dataclass
class Entry:
    seq: int
    interval: int
    sender: int
    receiver: int
    kwh_sent: float
    kwh_received: float
    price_ngn_per_kwh: float
    amount_kobo: int

    def canonical(self) -> str:
        return (
            f"{self.seq}|{self.interval}|{self.sender}|{self.receiver}|"
            f"{self.kwh_sent:.9f}|{self.kwh_received:.9f}|"
            f"{self.price_ngn_per_kwh:.4f}|{self.amount_kobo}"
        )


def _hash(prev: str, entry: Entry) -> str:
    return hashlib.sha256((prev + entry.canonical()).encode()).hexdigest()


@dataclass
class Ledger:
    price_ngn_per_kwh: float
    entries: list[Entry] = field(default_factory=list)
    hashes: list[str] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.hashes[-1] if self.hashes else GENESIS

    def append(
        self, interval: int, sender: int, receiver: int, kwh_sent: float, kwh_received: float, price: float | None = None
    ) -> Entry:
        """Add one transfer. `price` overrides the ledger's default price in NGN/kWh."""
        price = self.price_ngn_per_kwh if price is None else price
        if sender == receiver:
            raise ValueError("sender and receiver must differ")
        if kwh_sent < 0 or kwh_received < 0 or kwh_received > kwh_sent + 1e-12:
            raise ValueError("invalid energy amounts")
        e = Entry(
            seq=len(self.entries),
            interval=int(interval),
            sender=int(sender),
            receiver=int(receiver),
            kwh_sent=float(kwh_sent),
            kwh_received=float(kwh_received),
            price_ngn_per_kwh=float(price),
            amount_kobo=int(round(kwh_received * price * 100)),
        )
        self.entries.append(e)
        self.hashes.append(_hash(self.head, e))
        return e

    def verify(self) -> bool:
        """Recompute the chain. False if any entry or hash was altered."""
        if len(self.entries) != len(self.hashes):
            return False
        prev = GENESIS
        for i, (e, h) in enumerate(zip(self.entries, self.hashes)):
            if e.seq != i:
                return False
            prev = _hash(prev, e)
            if prev != h:
                return False
        return True

    def first_invalid(self) -> int | None:
        """Index of the first entry whose hash does not verify, or None."""
        prev = GENESIS
        for i, (e, h) in enumerate(zip(self.entries, self.hashes)):
            prev = _hash(prev, e)
            if prev != h or e.seq != i:
                return i
        if len(self.entries) != len(self.hashes):
            return min(len(self.entries), len(self.hashes))
        return None

    def to_frame(self) -> pd.DataFrame:
        cols = ["seq", "interval", "sender", "receiver", "kwh_sent", "kwh_received", "price_ngn_per_kwh", "amount_kobo"]
        df = pd.DataFrame([[getattr(e, c) for c in cols] for e in self.entries], columns=cols)
        df["hash"] = self.hashes
        return df

    def netting(self, n_households: int, interval_to_period: np.ndarray | None = None) -> pd.DataFrame:
        """Per-period, per-household net energy and money.

        Positive kobo means the household is owed money (net seller).
        `interval_to_period` maps an interval index to a period label (e.g. day
        number). Without it, everything is one period.
        """
        rows: dict[tuple[int, int], list[float]] = {}
        for e in self.entries:
            p = int(interval_to_period[e.interval]) if interval_to_period is not None else 0
            for hh, sign_kwh, sign_kobo in ((e.sender, -e.kwh_sent, e.amount_kobo), (e.receiver, e.kwh_received, -e.amount_kobo)):
                r = rows.setdefault((p, hh), [0.0, 0])
                r[0] += sign_kwh
                r[1] += sign_kobo
        df = pd.DataFrame(
            [(p, hh, v[0], v[1]) for (p, hh), v in sorted(rows.items())],
            columns=["period", "household", "net_kwh", "net_kobo"],
        )
        return df

    def statements(self, n_households: int) -> pd.DataFrame:
        """Per-household totals over the whole ledger."""
        sold = np.zeros(n_households)
        bought = np.zeros(n_households)
        paid = np.zeros(n_households, dtype=np.int64)
        earned = np.zeros(n_households, dtype=np.int64)
        n_tx = np.zeros(n_households, dtype=np.int64)
        for e in self.entries:
            sold[e.sender] += e.kwh_sent
            bought[e.receiver] += e.kwh_received
            earned[e.sender] += e.amount_kobo
            paid[e.receiver] += e.amount_kobo
            n_tx[e.sender] += 1
            n_tx[e.receiver] += 1
        return pd.DataFrame(
            {
                "household": np.arange(n_households),
                "kwh_sold": sold,
                "kwh_bought": bought,
                "ngn_earned": earned / 100.0,
                "ngn_paid": paid / 100.0,
                "ngn_net": (earned - paid) / 100.0,
                "transactions": n_tx,
            }
        )
