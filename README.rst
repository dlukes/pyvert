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

XML
---

The vertical format is not valid XML; however, for ease of processing,
reliability and sanity, many of the ``vrt`` commands rely on parsing it as XML.
These are some of the consequences:

1. ``&``, ``<`` and ``>`` in positions will be escaped as XML entities
   (otherwise the file cannot be parsed); all other XML entities, as well as
   HTML entity references, will get converted to regular characters if the
   output encoding supports them. Run ``vrt unescape`` as a final step to get a
   consistent result by replacing all entities with regular codepoints, **which
   is always what you want in linguistics anyway**. There are currently no plans
   to add functionality so that entities re-emerge unscathed on the far side of
   the pipeline, because they shouldn't have been in the input data in the first
   place.
2. In order to reliably distinguish angled brackets which are part of structure
   tags from those which are part of positions (and escape the latter ones), a
   list of valid structure names is kept in ``pyvert.STRUCTURES``. All other
   structure tags will be escaped, unless you ``export
   VRT_STRUCTURES="additional accepted structure names"``. You will be warned if
   something that looks like it might be a structure has been escaped.

API
---

Each ``vrt`` command also exists as a generator function in the ``pyvert.vrt``
namespace, which takes a filehandle to an unparsed vertical as input and yields
the requested chunks. Thus, apart from the command line, the same functionality
is easily accessible as a library for scripting from within Python.

Since there's an asymmetry between the input and output of these generator
functions (line by line vs. chunk by chunk), use the ``linewise()`` function to
combine them into a pipeline like so:

.. code:: python

  from pyvert.vrt import filter, group, linewise

  filtered = filter(filehandle, ...)
  grouped = group(linewise(filtered), ...)

  for chunk in grouped:
      print(chunk)

Since these are all generator functions, even large files can be processed in a
memory-efficient way, provided that no part of the pipeline results in the
creation of excessively big chunks.

Note
====

This project has been set up using PyScaffold 2.5.3. For details and usage
information on PyScaffold see http://pyscaffold.readthedocs.org/.

License
=======

Copyright © 2016 `ÚČNK <http://korpus.cz>`_/David Lukeš

Distributed under the `GNU General Public License v3
<http://www.gnu.org/licenses/gpl-3.0.en.html>`_.
