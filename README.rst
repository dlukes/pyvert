******
pyvert
******

Python tools for processing corpora in the vertical format.

Description
===========

A library and assorted command line tools for slicing and dicing files in the
so-called *vertical* format, which are tantalizingly close to valid XML but not
quite there.

Installation
============

Clone from GitHub and use ``pip``::

  git clone git@github.com:dlukes/pyvert.git
  cd pyvert
  pip install --user [--editable] .

A ``vrt`` command is installed as the CLI interface to the library. See ``vrt
--help`` for details on **global options** and a list of available commands, and
``vrt COMMAND --help`` for **command options**.

Requirements and compatibility
==============================

See ``requirements.txt``. Only tested on Python 3.5.

Usage tips
==========

Pipeline
--------

When running a pipeline of ``vrt`` commands, it is useful to specify the
``--id`` global option in order to be able to disentangle the log messages from
the various invocations.

Encoding errors
---------------

Python's default encoding error handler is ``strict``, which means it just
croaks whenever it encounters a byte in a stream that doesn't correspond to the
expected encoding. For more graceful behavior, consider passing `one of the
alternative handlers <https://docs.python.org/3/library/functions.html#open>`_
with the ``--errors`` global option.

For data which should mostly be in a known encoding but might possibly have some
stray bytes here and there, ``replace`` is a good option (invalid bytes are
substituted with ``�``). When using commands that don't rely on parsing the
vertical as XML (e.g. ``filter``), you can also try to round trip the invalid
bytes with ``surrogateescape``.

Note
====

This project has been set up using PyScaffold 2.5.3. For details and usage
information on PyScaffold see http://pyscaffold.readthedocs.org/.

License
=======

Copyright © 2016 `ÚČNK <http://korpus.cz>`_/David Lukeš

Distributed under the `GNU General Public License v3
<http://www.gnu.org/licenses/gpl-3.0.en.html>`_.
