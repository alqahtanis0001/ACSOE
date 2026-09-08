"""Tests for `scripts/verify.py`. Specs 00, 01 and 02.

`verify.py` is what decides whether anything else in this project is done, so it
gets tested like the load-bearing thing it is: the runner's result precedence and
exit codes, every Phase 0 criterion proved twice (PENDING on an unbuilt tree and
PASS against a fabricated subject), and `docs_vocabulary` proved to actually FAIL
on a planted term.
"""
