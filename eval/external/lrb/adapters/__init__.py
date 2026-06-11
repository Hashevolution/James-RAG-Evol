"""LRB SUT adapters: Vanilla + Naive-supersede + JAMES (Phase A/B)."""
from .vanilla import VanillaRagAdapter
from .naive_supersede import NaiveSupersedeAdapter
from .james import JamesValidityAdapter

__all__ = ["VanillaRagAdapter", "NaiveSupersedeAdapter",
           "JamesValidityAdapter"]
