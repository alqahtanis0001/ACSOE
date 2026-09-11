"""The manager: five screens over the archive, the registry and SSH.

It reads files and runs ``ssh``. It never records, it never writes to the SQLite
store — engine 19 ``memory`` is the single writer of every relational row — and
it never opens a connection that a node could open back.
"""
