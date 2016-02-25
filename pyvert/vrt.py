import click
from click._compat import open_stream
from click.utils import safecall
import logging

import random
import pyvert
from lxml import etree

# prevent chatty BrokenPipe errors
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)

ENC_ERR_HNDLRS = ["strict", "ignore", "replace", "surrogateescape",
                  "xmlcharrefreplace", "backslashreplace", "namereplace"]


def log_invocation(cx):
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


@click.group(context_settings=dict(obj={}))
@click.pass_context
@click.option("-i", "--input", type=click.File("r", lazy=True), default="-",
              help="Path to vertical to process (default: STDIN).")
@click.option("--inenc", type=str, default="utf-8", help="Input encoding.")
@click.option("--outenc", type=str, default="utf-8", help="Output encoding.")
@click.option("--errors", default="strict", type=click.Choice(ENC_ERR_HNDLRS),
              help="How to handle encoding errors.")
@click.option("--id", type=str, default="",
              help="Give an ID to this call to distinguish it in the logs.")
@click.option("-l", "--log", help="Logging verbosity.", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def vrt(cx, input, inenc, outenc, errors, id, log):
    """Slice and dice a corpus in vertical format.

    Available COMMANDs are listed below and are documented with ``vrt COMMAND
    --help``.

    """
    input, should_close = open_stream(input.name, "r", encoding=inenc,
                                      errors=errors)
    if should_close:
        cx.call_on_close(safecall(input.close))
    else:
        cx.call_on_close(safecall(input.flush))
    cx.obj.update(input=input, inenc=inenc, outenc=outenc, errors=errors,
                  log=log)
    top_command = cx.command.name + ("({})".format(id) if id else "")
    logging.basicConfig(level=log, format="[%(asctime)s " + top_command +
                        "/%(command)s:%(levelname)s] %(message)s")


@vrt.command()
@click.pass_context
@click.option("-a", "--ancestor", default="doc", type=str,
              help="The structure to split into chunks.")
@click.option("-c", "--child", default="s", type=str,
              help="The structure that the chunks will consist of.")
@click.option("-n", "--name", default="chunk", type=str,
              help="The name to give to the added chunk structures.")
@click.option("-m", "--minmax", default=(2000, 5000), type=(int, int),
              help="The minimum and maximum length of a chunk.")
def chunk(cx, ancestor, child, name, minmax):
    """Split a vertical into chunks of a given size.

    Output is that same vertical, but separated into chunks. All structures
    other than ``--ancestor``, the chunks themselves and ``--child`` are
    discarded.

    ``--ancestor`` is the existing structure on which to base the chunks; its
    metadata will be copied over to the newly created chunks.

    ``--child`` is the structure which will constitute the immediate children
    of the chunks and whose boundaries the chunks will respect.

    Note that ``--minmax`` may be violated when the given ancestor structure is
    shorter, or when the next child boundary occurs some positions after the
    maximum limit.

    """
    log_invocation(cx)
    # we want the chunking to be randomized within the minmax range, but
    # replicable across runs on the same data
    random.seed(1)
    for struct in pyvert.iterstruct(cx.obj["input"], struct=ancestor):
        chunkified = struct.chunk(child=child, name=name, minmax=minmax)
        click.echo(etree.tostring(chunkified, encoding=cx.obj["outenc"]))


@vrt.command()
@click.option("-p", "--parent", default=None, type=str,
              help="Structure which will immediately dominate the groups.")
@click.option("-t", "--target", default="sp", type=str,
              help="Structure which will be grouped.")
@click.option("-a", "--attr", default=["oznacenishody"], type=str, multiple=True,
              help="Attribute(s) by which to group.")
@click.option("--as", "as_struct", default="group", type=str,
              help="Tag name of the group structures.")
@click.pass_context
def group(cx, parent, target, attr, as_struct):
    """Group structures in vertical according to an attribute.

    Group all ``--target`` structures within each ``--parent`` structure
    according to one or more of their ``--attr``ibute values.

    Structures above parent and between parent and target are discarded. Groups
    will be represented as structures with tag <``--as``> and an @id attribute
    with the same value as the original attr. Other attributes are copied over
    from the first target falling into the given group, and from the parent.

    """
    log_invocation(cx)
    for i, struct in enumerate(pyvert.iterstruct(cx.obj["input"], struct=parent)):
        grouped = struct.group(target=target, attr=attr, as_struct=as_struct,
                               fallback_root_id="__autoid{}__".format(i))
        click.echo(etree.tostring(grouped, encoding=cx.obj["outenc"]))


@vrt.command()
@click.option("-s", "--struct", default="doc", type=str,
              help="Structures into which the vertical will be split.")
@click.option("-a", "--attr", required=True, type=(str, str), multiple=True,
              help="Attribute key/value pair(s) to filter by.")
@click.option("--all", "test", flag_value="issuperset", default=True,
              help="Struct must match all ``--attr key val`` pairs to pass.")
@click.option("--any", "test", flag_value="intersection",
              help="Struct can match any ``--attr key val`` pair to pass.")
@click.pass_context
def filter(cx, struct, attr, test):
    """Filter structures in vertical according to attribute value(s).

    All structures above ``--struct`` are discarded. The output is a vertical
    consisting of structures of type struct which satisfy ``--all/--any``
    ``--attr key val`` conditions.

    """
    log_invocation(cx)
    attr = set(attr)
    for struct in pyvert.iterstruct(cx.obj["input"], struct=struct):
        struct_attr = set(struct.attr.items())
        # check if struct_attr is a superset of attr (if test == "all") or
        # whether the intersection of struct_attr and attr is non-zero (if
        # test == "any")
        if getattr(struct_attr, test)(attr):
            click.echo(struct.raw.encode(cx.obj["outenc"], errors=cx.obj["errors"]),
                       nl=False)
