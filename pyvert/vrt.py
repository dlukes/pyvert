import io
import click
import functools
import logging

import random
import pyvert
from lxml import etree

# prevent chatty BrokenPipe errors
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)

ENC_ERR_HNDLRS = ["strict", "ignore", "replace", "surrogateescape",
                  "xmlcharrefreplace", "backslashreplace", "namereplace"]
API = {}

#####################
# Utility functions #
#####################


def _log_invocation(cx):
    caller = cx.command.name

    def log(opt, val):
        dash = "-" if len(opt) == 1 else "--"
        logging.info("  {}{}: {}".format(dash, opt, val),
                     extra=dict(command=caller))

    logging.info("Global parameters:", extra=dict(command=caller))
    for opt, val in cx.obj.items():
        log(opt, val)
    logging.info("Command parameters:", extra=dict(command=caller))
    for opt, val in cx.params.items():
        log(opt, val)


def _option(*args, **kwargs):
    return click.option(*args, show_default=True, **kwargs)


def _add2api(func):
    """Store a function by name in the API dictionary so that it can be reinstated
    in the global namespace instead of its decorated counterpart, which is not
    useful for programming with (see end of this file).

    """
    API[func.__name__] = func
    return func


def _genfunc2comm(gen_func):
    """Turn a generator function (which is a better and more elegant API
    abstraction) into a function which can be used as a click command callback.

    """
    @functools.wraps(gen_func)
    def command(cx, **kwargs):
        _log_invocation(cx)
        for chunk in gen_func(cx.obj["input"], **kwargs):
            click.echo(chunk.encode(cx.obj["outenc"], errors=cx.obj["errors"]),
                       nl=False)

    return command


def linewise(chunks):
    """Iterate over vertical chunks in a linewise fashion.

    Useful for composing functions that expect a filehandle to an unparsed
    vertical as input and return vertical chunks as strings (for efficiency
    purposes when outputting to the terminal -- it's faster to encode on a
    chunk-by-chunk basis rather than line-by-line).

    This makes it easy to chain operations directly in a Python script:

        filtered = vrt.filter(filehandle, ...)
        grouped = vrt.group(linewise(filtered), ...)

    """
    for chunk in chunks:
        yield from io.StringIO(chunk)


############
# Commands #
############


@click.group(context_settings=dict(obj={}))
@click.pass_context
@_option("-i", "--input", type=click.File("r", lazy=True), default="-",
         help="Path to vertical to process (- for STDIN).")
@_option("--inenc", type=str, default="utf-8", help="Input encoding.")
@_option("--outenc", type=str, default="utf-8", help="Output encoding.")
@_option("--errors", default="strict", type=click.Choice(ENC_ERR_HNDLRS),
         help="How to handle encoding errors.")
@_option("--id", type=str, default="",
         help="Give an ID to this call to distinguish it in the logs.")
@_option("-l", "--log", help="Logging verbosity.", default="INFO",
         type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def vrt(cx, input, inenc, outenc, errors, id, log):
    """Slice and dice a corpus in vertical format.

    Available COMMANDs are listed below and are documented with ``vrt COMMAND
    --help``.

    """
    input = click.File("r", encoding=inenc, errors=errors)(input.name, ctx=cx)
    cx.obj.update(input=input, inenc=inenc, outenc=outenc, errors=errors,
                  log=log)
    top_command = cx.command.name + ("({})".format(id) if id else "")
    logging.basicConfig(level=log, format="[%(asctime)s " + top_command +
                        "/%(command)s:%(levelname)s] %(message)s")


@vrt.command()
@click.pass_context
@_option("-a", "--ancestor", default="doc", type=str,
         help="The structure to split into chunks.")
@_option("-c", "--child", default="s", type=str,
         help="The structure that the chunks will consist of.")
@_option("-n", "--name", default="chunk", type=str,
         help="The name to give to the added chunk structures.")
@_option("-m", "--minmax", default=(2000, 5000), type=(int, int),
         help="The minimum and maximum length of a chunk.")
@_genfunc2comm
@_add2api
def chunk(vertical, ancestor, child, name="chunk", minmax=(2000, 5000)):
    """Split a vertical into chunks of a given size.

    Output is that same vertical, but separated into chunks. All structures
    other than ``ancestor``, the chunks themselves and ``child`` are discarded.

    ``ancestor`` is the existing structure on which to base the chunks; its
    metadata will be copied over to the newly created chunks.

    ``child`` is the structure which will constitute the immediate children of
    the chunks and whose boundaries the chunks will respect.

    Note that ``minmax`` may be violated when the given ancestor structure is
    shorter, or when the next child boundary occurs some positions after the
    maximum limit.

    """
    # we want the chunking to be randomized within the minmax range, but
    # replicable across runs on the same data
    random.seed(1)
    for struct in pyvert.iterstruct(vertical, struct=ancestor):
        chunkified = struct.chunk(child=child, name=name, minmax=minmax)
        yield etree.tostring(chunkified)


@vrt.command()
@click.pass_context
@_option("-p", "--parent", default=None, type=str,
         help="Structure which will immediately dominate the groups.")
@_option("-t", "--target", default="sp", type=str,
         help="Structure which will be grouped.")
@_option("-a", "--attr", default=["oznacenishody"], type=str, multiple=True,
         help="Attribute(s) by which to group.")
@_option("--as", "as_struct", default="group", type=str,
         help="Tag name of the group structures.")
@_genfunc2comm
@_add2api
def group(vertical, parent, target, attr, as_struct="group"):
    """Group structures in vertical according to an attribute.

    Group all ``target`` structures within each ``parent`` structure
    according to one or more of their ``attr``ibute values.

    Structures above parent and between parent and target are discarded. Groups
    will be represented as structures with tag <``as``> and an @id attribute
    with the same value as the original attr. Other attributes are copied over
    from the first target falling into the given group, and from the parent.

    """
    for i, struct in enumerate(pyvert.iterstruct(vertical, struct=parent)):
        grouped = struct.group(target=target, attr=attr, as_struct=as_struct,
                               fallback_root_id="__autoid{}__".format(i))
        yield etree.tostring(grouped)


@vrt.command()
@click.pass_context
@_option("-s", "--struct", default="doc", type=str,
         help="Structures into which the vertical will be split.")
@_option("-a", "--attr", required=True, type=(str, str), multiple=True,
         help="Attribute key/value pair(s) to filter by.")
@_option("-m", "--match", default="all", type=click.Choice(["all", "any"]),
         help="Match condition for ``--attr key val`` pairs.")
@_genfunc2comm
@_add2api
def filter(vertical, struct, attr, match="all"):
    """Filter structures in vertical according to attribute value(s).

    All structures above ``struct`` are discarded. The output is a vertical
    consisting of structures of type struct which satisfy ``all/any`` ``(key,
    val)`` conditions in ``attr``.

    """
    attr = set(attr)
    if match == "all":
        match = "issuperset"
    elif match == "any":
        match = "intersection"
    else:
        raise RuntimeError("Unsupported matching strategy: {}.".format(match))
    for struct in pyvert.iterstruct(vertical, struct=struct):
        struct_attr = set(struct.attr.items())
        # check if struct_attr is a superset of attr (if match == "all") or
        # whether the intersection of struct_attr and attr is non-zero (if
        # match == "any")
        if getattr(struct_attr, match)(attr):
            yield struct.raw


@vrt.command()
@click.pass_context
@_option("-p", "--parent", default="doc", type=str,
         help="Structure *parent* which metadata will be projected.")
@_option("-c", "--child", default="text", type=str,
         help="Structure *child* which metadata will be projected.")
@_genfunc2comm
@_add2api
def project(vertical, parent, child):
    """Project metadata from ``parent`` structure onto ``child`` structure.

    Projected attributes are prefixed with the parent structure's name, and if
    necessary, postfixed with underscores so as to avoid collisions with any
    existing attributes in the child structure.

    """
    for struct in pyvert.iterstruct(vertical, struct=parent):
        struct.project(child=child)
        yield etree.tostring(struct.xml)


# now that all commands are defined, restore the original generator functions
# in the global namespace to serve as an API which can be used from Python by
# importing ``pyvert.vrt``
globals().update(API)
