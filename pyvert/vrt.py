import os
import io
import click
import functools
import logging

import regex as re
import random
import pyvert
import html
from lxml import etree

# prevent chatty BrokenPipe errors
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)

ENC_ERR_HNDLRS = ["strict", "ignore", "replace", "surrogateescape",
                  "xmlcharrefreplace", "backslashreplace", "namereplace"]
API = {}
PYVERT_STRUCTS = os.environ.get("PYVERT_STRUCTS", "").split()

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
        logger = logging.getLogger()
        for i, chunk in enumerate(gen_func(cx.obj["input"], **kwargs)):
            if logger.getEffectiveLevel() <= logging.INFO:
                click.echo("\rOutputting vertical fragment #{}.".format(i),
                           err=True, nl=False)
            click.echo(chunk.encode(cx.obj["outenc"], errors=cx.obj["errors"]),
                       nl=False)

    return command


def linewise(chunks):
    """Iterate over vertical chunks in a linewise fashion.

    Useful for composing generator functions that expect a filehandle to an
    unparsed vertical (which will be read line by line) as input and yield
    chunks of the vertical as strings. Linewise yielding is not their default
    behavior because when outputting to the terminal, it's faster to encode on
    a chunk-by-chunk basis rather than line-by-line.

    ``linewise()`` makes it easy to chain operations on a vertical directly in
    a Python script:

        filtered = vrt.filter(filehandle, ...)
        grouped = vrt.group(linewise(filtered), ...)

    """
    if isinstance(chunks, str):
        yield from io.StringIO(chunks)
    else:
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

    NOTE: In order to speed up processing to a degree, you can provide a list
    of strings to be considered valid structure names in the ``PYVERT_STRUCTS``
    environment variable. If provided, the list must be exhaustive, otherwise
    unknown tags might be XML-escaped. If unsure, leave it unset, valid tags
    will be detected automatically, which is somewhat slower but safer.

    """
    if PYVERT_STRUCTS:
        pyvert.config(structs=PYVERT_STRUCTS)
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
    for i, struct in enumerate(pyvert.iterstruct(vertical, struct=ancestor)):
        chunkified = struct.chunk(child=child, name=name, minmax=minmax,
                                  fallback_orig_id="__autoid{}__".format(i))
        yield etree.tounicode(chunkified)


@vrt.command()
@click.pass_context
@_option("-t", "--target", default="sp", type=str,
         help="Structure which will be grouped.")
@_option("-a", "--attr", default=["oznacenishody"], type=str, multiple=True,
         help="Attribute(s) by which to group.")
@_option("-p", "--parent", default=None, type=str,
         help="Structure which will immediately dominate the groups.")
@_option("-u", "--unique", default=False, is_flag=True,
         help="Grouping attributes are unique identifiers.")
@_option("--as", "as_struct", default="group", type=str,
         help="Tag name of the group structures.")
@_genfunc2comm
@_add2api
def group(vertical, target, attr, parent=None, unique=False, as_struct="group"):
    """Group structures in vertical according to an attribute.

    Group all ``target`` structures within each ``parent`` structure
    according to one or more of their ``attr``ibute values.

    Structures above parent and between parent and target are discarded. Groups
    will be represented as structures with tag <``as``> and an @id attribute
    with the same value as the original attr. Other attributes are copied over
    from the first target falling into the given group, and from the parent.

    If no ``parent`` is given, groups will be constructed at the top level of
    the vertical.

    """
    for i, struct in enumerate(pyvert.iterstruct(vertical, struct=parent)):
        fri = None if unique else "__autoid{}__".format(i)
        grouped = struct.group(target=target, attr=attr, as_struct=as_struct,
                               fallback_root_id=fri)
        serialized = etree.tounicode(grouped)
        # get rid of helper <root/> struct wrapping the vertical to make it
        # valid XML when it's taken as a whole
        if parent is None:
            serialized = serialized[7:-8]
        yield serialized


@vrt.command()
@click.pass_context
@_option("-s", "--struct", default="doc", type=str,
         help="Structures into which the vertical will be split.")
@_option("-a", "--attr", required=True, type=(str, str), multiple=True,
         help="Attribute key/value pair(s) to filter by.")
@_option("-m", "--match", default="all", type=click.Choice(["all", "any", "none"]),
         help="Match condition for ``--attr key val`` pairs.")
@_genfunc2comm
@_add2api
def filter(vertical, struct, attr, match="all"):
    """Filter structures in vertical according to attribute value(s).

    All structures above ``struct`` are discarded. The output is a vertical
    consisting of structures of type struct which satisfy ``all/any/none``
    ``(key, val)`` conditions in ``attr``.

    """
    # TODO: reimplement this as a regex match on a string generated from the
    # sorted attr list → will allow for wildcard matching
    attr = set(attr)
    if match == "all":
        match = "issuperset"
    elif match == "any":
        match = "intersection"
    elif match == "none":
        match = "isdisjoint"
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
         help="Parent structure whose metadata will be projected.")
@_option("-c", "--child", default="text", type=str,
         help="Child structure onto which metadata will be projected.")
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
        yield etree.tounicode(struct.xml)


@vrt.command()
@click.pass_context
@_option("--no-recursive", is_flag=True, default=False,
         help="Remove only one layer of entitity escaping.")
@_genfunc2comm
@_add2api
def unescape(vertical, no_recursive=False):
    """Replace XML entities and HTML entity references with codepoints.

    """
    for line in vertical:
        line = line.strip() + "\n"
        esc = html.unescape(line)
        if no_recursive:
            yield esc
        else:
            while esc != line:
                esc, line = html.unescape(esc), esc
            yield esc


@vrt.command()
@click.pass_context
@_option("-t", "--target", default="doc", type=str,
         help="Structure to wrap.")
@_option("-a", "--attr", required=True, type=str, multiple=True,
         help="Attributes to group by (if shared by adjacent structures).")
@_option("-n", "--name", default="wrap", type=str,
         help="Name of the wrapping structure.")
@_genfunc2comm
@_add2api
def wrap(vertical, target, attr, name="wrap"):
    """Wrap ``target`` structures in a parent with tag ``name``.

    Put adjacent structures under the same parent while their attribute ``key,
    val`` pairs (for all attributes specified under ``attr``) are the same.

    """
    last_attr = None
    for i, struct in enumerate(pyvert.iterstruct(vertical, struct=target)):
        try:
            new_attr = ",".join(struct.attr[a] for a in attr)
        except KeyError as e:
            raise RuntimeError("Structure does not contain specified "
                               "attribute.") from e
        if new_attr != last_attr:
            if last_attr is not None:
                yield "</{}>\n".format(name)
            yield '<{} id="{}_{}">\n'.format(name, new_attr, i)
        yield struct.raw
        last_attr = new_attr
    yield "</{}>\n".format(name)


@vrt.command()
@click.pass_context
@_option("-s", "--struct", default="doc", type=str,
         help="Structure to add an identifier to.")
@_option("-b", "--base", default="id_", type=str,
         help="The common base of the identifier string.")
@_option("-a", "--attr", default="id", type=str,
         help="Name of the identifier attribute to add/overwrite.")
@_genfunc2comm
@_add2api
def identify(vertical, struct, base="id_", attr="id"):
    """Add a unique identifier attribute to each ``struct`` in vertical, and
    hoist the struct to the top level of the vertical.

    The identifier will be stored in attribute ``attr`` (possibly overwriting
    it) and will be of the form ``<base>_<numeric index>``.

    """
    # TODO: iterate over lines instead so as not to drop structures above
    # ``struct`` (→ change docstring when it's done)
    for i, struct in enumerate(pyvert.iterstruct(vertical, struct=struct)):
        struct.xml.attrib[attr] = base + str(i)
        yield etree.tounicode(struct.xml)


@vrt.command()
@click.pass_context
@_option("-t", "--tagger", type=click.Path(exists=True, dir_okay=False),
         required=True, help="Path to tagger file to use.")
@_option("-s", "--struct", type=str, multiple=True, default=PYVERT_STRUCTS,
         help="Strings to be considered valid struct names.")
@_option("-d", "--sent", type=str, multiple=True, required=True,
         help="Name(s) of struct(s) which delimit sentences.")
@_option("-x/-X", "--extended/--no-extended",
         help="Output extended ID or bare lemmas (when applicable).")
@_option("-g/-G", "--guesser/--no-guesser",
         help="Use morphological guesser (when available).")
@_genfunc2comm
@_add2api
def tag(vertical, tagger, struct, sent, extended, guesser):
    """Tag vertical using MorphoDiTa.

    A list of valid ``struct`` names must be explicitly provided, either via
    the corresponding parameter (used repeatedly if necessary) or via the
    ``PYVERT_STRUCTS`` environment variable.

    """
    if not struct:
        raise RuntimeError(
            "A list of valid ``struct`` names must be explicitly provided, "
            "either via the corresponding parameter (used repeatedly if "
            "necessary) or via the ``PYVERT_STRUCTS`` environment variable.")
    struct = re.compile("^</?(?:" + "|".join(struct) + ").*?>")
    sent_end = re.compile("^</(?:" + "|".join(sent) + ")\s*>")
    try:
        import ufal.morphodita as md
    except ImportError as e:
        raise RuntimeError(
            "The ``tag`` subcommand needs the MorphoDiTa library and its Python "
            "bindings; see http://ufal.mff.cuni.cz/morphodita.") from e
    logging.info("Loading tagger.", extra=dict(command="tag"))
    tagger, tagger_file = md.Tagger.load(tagger), tagger
    if tagger is None:
        raise RuntimeError(
            "Unable to load tagger from file {}.".format(tagger_file))
    forms = md.Forms()
    lemmas = md.TaggedLemmas()
    tokens = md.TokenRanges()
    tokenizer = md.Tokenizer.newVerticalTokenizer()
    morpho = tagger.getMorpho()
    converter = md.TagsetConverter.newStripLemmaIdConverter(morpho)
    guesser = 1 if guesser else 0
    s_buffer = []
    t_buffer = ""
    for line in vertical:
        if sent_end.match(line):
            s_buffer.append(line)
            t_buffer += "\n"
            tokenizer.setText(t_buffer)
            tokenizer.nextSentence(forms, tokens)
            tagger.tag(forms, lemmas, morpho.NO_GUESSER)
            tagged_iter = zip(forms, lemmas)
            for s in s_buffer:
                if s is None:
                    w, l = next(tagged_iter)
                    import ipdb
                    ipdb.set_trace()

                    if not extended:
                        converter.convert(l)
                    yield "{}\t{}\t{}\n".format(w, l.lemma, l.tag)
                else:
                    yield s
            s_buffer = []
            t_buffer = ""
        elif struct.match(line):
            s_buffer.append(line)
        else:
            s_buffer.append(None)
            t_buffer += line
    # emit any remaining structs at the end of the file
    for s in s_buffer:
        if s is None:
            raise RuntimeError(
                "Unclosed sentence at end of file; either the vertical is "
                "malformed or the wrong structs were specified as sentence "
                "delimiters.")
        yield s


@vrt.command()
@click.pass_context
@_genfunc2comm
@_add2api
def strip(vertical):
    """Strip positional attributes other than the first one.

    """
    word = re.compile(r"^([^\t]+).*?(\s{0,2})$")
    struct = re.compile(r"^<.*?>\s*$")
    for line in vertical:
        if not struct.match(line):
            line = word.sub(r"\1\2", line)
        yield line


def decorate(vertical):
    """Add a sequential index to vertical positions.

    It is stored as the first positional attribute.

    """
    raise NotImplementedError()


def undecorate(decorated, original, prune=True):
    """Select positions from original vertical based on indices in decorated.

    If ``prune`` is True, remove empty structures from output.

    """
    raise NotImplementedError()


# now that all commands are defined, restore the original generator functions
# in the global namespace to serve as an API which can be used from Python by
# importing ``pyvert.vrt``
globals().update(API)
