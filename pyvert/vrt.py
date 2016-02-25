import os
import click
import logging

import random
import pyvert
from lxml import etree

# prevent chatty BrokenPipe errors
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)


def log_invocation(cx):
    logging.info("Global parameters:")
    logging.info("  --input: {}".format(cx.obj["input"]))
    logging.info("Command ``{}`` parameters:".format(cx.command.name))
    for opt, val in cx.params.items():
        dash = "-" if len(opt) == 1 else "--"
        logging.info("  {}{}: {}".format(dash, opt, val))


@click.group(context_settings=dict(obj={}))
@click.pass_context
@click.option("--input", help="Path to vertical to process (default: STDIN).",
              type=click.File("r"), default="-")
@click.option("--log", help="Logging verbosity.", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def vrt(cx, input, log):
    """Slice and dice a corpus in vertical format.

    Available COMMANDs are listed below and are documented with ``vrt COMMAND
    --help``.

    """
    cx.obj["input"] = input
    logging.basicConfig(level=log, format="[%(asctime)s " +
                        os.path.basename(__file__) +
                        ":%(levelname)s] %(message)s")


@vrt.command()
@click.pass_context
@click.option("--ancestor", help="The structure to split into chunks.",
              default="doc", type=str)
@click.option("--child", help="The structure that the chunks will consist of.",
              default="s", type=str)
@click.option("--name", help="The name to give to the added chunk structures.",
              default="chunk", type=str)
@click.option("--minmax", help="The minimum and maximum length of a chunk.",
              default=(2000, 5000), type=(int, int))
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
        print(etree.tostring(chunkified, encoding="unicode"))


@vrt.command()
@click.option("--parent", default="doc", type=str,
              help="The structure which will immediately dominate the groups.")
@click.option("--target", default="sp", type=str,
              help="The structure which will be grouped.")
@click.option("--attr", default="oznacenishody", type=str,
              help="The attribute by which to group.")
@click.option("--as", "as_struct", default="group", type=str,
              help="The tag name of the group structures.")
@click.pass_context
def group(cx, parent, target, attr, as_struct):
    """Group structures in vertical according to an attribute.

    Group all ``--target`` structures within each ``--parent`` structure
    according to one (TODO or more?) of their ``--attr``ibute values.

    Structures above parent and between parent and target are discarded. Groups
    will be represented as structures with tag <``--as``> and an @id attribute
    with the same value as the original attr. Other attributes are copied over
    from the first target falling into the given group, and from the parent.

    """
    log_invocation(cx)
    for struct in pyvert.iterstruct(cx.obj["input"], struct=parent):
        grouped = struct.group(target=target, attr=attr, as_struct=as_struct)
        print(etree.tostring(grouped, encoding="unicode"))


@vrt.command()
@click.option("--struct", default="doc", type=str,
              help="Structures into which the vertical will be split.")
@click.option("--attr", required=True, type=(str, str), multiple=True,
              help="Attribute key/value pair(s) to filter by.")
@click.option("--all", "quant", flag_value="issuperset", default=True,
              help="Struct must match all ``--attr key val`` pairs to pass.")
@click.option("--any", "quant", flag_value="intersection",
              help="Struct can match any ``--attr key val`` pair to pass.")
@click.pass_context
def filter(cx, struct, attr, quant):
    """Filter structures in vertical according to attribute value(s).

    All structures above ``--struct`` are discarded. The output is a vertical
    consisting of structures of type struct which satisfy ``--all/--any``
    ``--attr key val`` conditions.

    """
    log_invocation(cx)
    attr = set(attr)
    for struct in pyvert.iterstruct(cx.obj["input"], struct=struct):
        struct_attr = set(struct.attr.items())
        # check if struct_attr is a superset of attr (if quant == "all") or
        # whether the intersection of struct_attr and attr is non-zero (if
        # quant == "any")
        if getattr(struct_attr, quant)(attr):
            print(struct.raw, end="")
