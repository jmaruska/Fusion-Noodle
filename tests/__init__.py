"""Tests that run outside Fusion.

Rule: these cover pure logic only. The `adsk` modules are stubbed so the backend
imports, but no test asserts on what a Fusion API call returns. Anything whose
answer comes from Fusion (geometry, selections, timeline, undo) is tested in
Fusion itself.

Run from the repo root:  python3 -m unittest discover -s tests -t .
"""
