"""The Recording Manager: running recorders on several machines, one archive.

Nothing in this package imports from ``acsoe``. Two of the files in it —
``record.py``'s sibling ``supervise.py`` and the node packages built by the
manager — are copied to machines that have no checkout of this project, and a
single import would end that.

``scripts/`` is not a package, so this one is reached by putting ``scripts/`` on
``sys.path``; ``manager/serve.py`` does that and is the entry point.
"""
