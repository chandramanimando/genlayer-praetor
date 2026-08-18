"""Stub the genlayer runtime so the contract is unit-testable off-chain."""
import sys
import types

genlayer = types.ModuleType("genlayer")


class Contract:
    def __init__(self):
        pass


class _Decorators:
    @staticmethod
    def entry(fn):
        return fn

    @staticmethod
    def view(fn):
        return fn

    @staticmethod
    def equivalence(fn):
        return fn


genlayer.Contract = Contract
genlayer.contract = _Decorators()
sys.modules["genlayer"] = genlayer
