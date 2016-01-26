import os
import click
import logging

import random
import pyvert
from lxml import etree


@click.group()
@click.option("--log", help="Logging verbosity.", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def vrt(log):
    logging.basicConfig(level=log, format="[%(asctime)s " +
                        os.path.basename(__file__) +
                        ":%(levelname)s] %(message)s")


@vrt.command()
@click.argument("input", type=click.File("r"))
@click.option("--ancestor", help="The structure to split into chunks.",
              default="doc", type=str)
@click.option("--child", help="The structure that the chunks will consist of.",
              default="s", type=str)
@click.option("--name", help="The name to give to the added chunk structures.",
              default="chunk", type=str)
@click.option("--minmax", help="The minimum and maximum length of a chunk.",
              default=(2000, 5000), type=(int, int))
def chunk(input, ancestor, child, name, minmax):
    """Split a vertical into chunks of a given size.

    Output is that same vertical, but separated into chunks. All structures
    other than ancestor, chunk and child are discarded.

    --ancestor is the existing structure on which to base the chunks; its
    metadata will be copied over to the newly created chunks.

    --child is the structure which will constitute the immediate children of
    the chunks and whose boundaries the chunks will respect.

    Note that --minmax may be violated when the given ancestor structure is
    shorter, or when the next child boundary occurs some positions after the
    maximum limit.

    """
    # we want the chunking to be randomized within the minmax range, but
    # replicable across runs on the same data
    random.seed(1)
    for struct in pyvert.iterstruct(input, struct=ancestor):
        chunkified = struct.chunks(child=child, name=name, minmax=minmax)
        print(etree.tostring(chunkified, encoding="unicode"))
        # verify that self.xml hasn't been modified
        # with open("test.xml", "w") as fh:
        #     print(etree.tostring(struct.xml, encoding="unicode"), file=fh)


@vrt.command()
def group():
    """Group all target structures within each parent structure according to
    one (TODO or more) of their attribute values.

    """
    click.echo("This works!")
