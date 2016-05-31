from itertools import chain
from lazy import lazy
from tempfile import NamedTemporaryFile as NamedTempFile

import regex as re
import random
from lxml import etree
from html import unescape

__all__ = ["Structure", "iterstruct", "config"]
__version__ = "0.0.0"

# disable security preventing DoS attacks with huge files
etree.set_default_parser(etree.ETCompatXMLParser(huge_tree=True))

STRUCTS = None


class Structure():
    """A structure extracted from a vertical.

    """
    def __init__(self, raw_vert, structs):
        self.raw = raw_vert.strip() + "\n"
        self.structs = structs
        first_line = self.raw.split("\n", maxsplit=1)[0]
        self.name = re.search(r"\w+", first_line).group()
        self.attr = dict(re.findall(r'(\w+)="(.*?)"', first_line))

    @lazy
    def xml(self):
        """The structure represented as an ElementTree.

        """
        xml = self._xmlize()
        try:
            xml = etree.fromstring(xml)
            xml.tail = "\n"
            return xml
        except etree.XMLSyntaxError as e:
            with NamedTempFile(mode="w", suffix=".xml", delete=False) as fh:
                fh.write(xml)
            e = str(e)
            e += "\nAn XMLSyntaxError occurred while processing a document. " \
                 "It has been dumped to {} for inspection.".format(fh.name)
            raise Exception(e)

    def chunk(self, child, name, minmax, fallback_orig_id=None):
        """Split the structure into chunks of a given size.

        :param name: The name to give to the XML element representing the
            chunks.
        :type name: str
        :param child: The child element of which the chunks will be composed
            and whose boundaries will be respected.
        :type child: str
        :param minmax: The length range the individual chunks should roughly
            fall into.
        :type minmax: (int, int)
        :param fallback_orig_id: If structure has no @id attribute, this will
            be used instead to generate the @ids of the chunks.
        :rtype: etree.Element

        """
        def chunk_pos(idx, total):
            if total <= 2:
                return "beginning" if idx == 0 else "end"
            else:
                # the threshold is 1 non-inclusive for a total of 3, 1 for 4, 2
                # for 5 etc.
                if idx < round(total / 3):
                    return "beginning"
                # the threshold is 2 non-inclusive for a total of 3, 2 for 4, 4
                # for 5 etc.
                elif idx < round(2 * total / 3):
                    return "middle"
                else:
                    return "end"

        root = etree.Element(self.xml.tag, attrib=self.xml.attrib)
        root.text = root.tail = "\n"

        def loop_vars(name, attrib, minmax):
            chunk = etree.Element(name, attrib=attrib)
            chunk.text = chunk.tail = "\n"
            chunk_length = random.randint(*minmax)
            return chunk, chunk_length, 0

        chunk, chunk_length, positions = loop_vars(name, root.attrib, minmax)
        for child in self.xml.iter(child):
            # we'll be modifying this, so no choice but to make a new one, or
            # else self.xml would end up modified
            new_child = etree.SubElement(chunk, child.tag, attrib=child.attrib)
            # the child might not directly contain text -- it might be a
            # paragraph, not a sentence; or, as in SYN2015, sentences might
            # contain lower-level structures like <hi> -- so first, get ALL the
            # text dominated by the child node
            text = child.xpath("string()")
            text = text.strip("\n")
            # collapse newlines
            text = re.sub(r"\n{2,}", "\n", text)
            # only NOW compute the number of positions
            positions += len(text.splitlines())
            # set the child's text (remember, if it was a paragraph to start
            # with, it only had newlines in its text)
            new_child.text = "\n" + text + "\n"
            new_child.tail = child.tail
            if positions >= chunk_length:
                root.append(chunk)
                chunk, chunk_length, positions = loop_vars(name, root.attrib, minmax)
        # after the for-loop ends, check if there's a final non-empty chunk
        # that didn't accumulate the required number of positions
        else:
            if positions > 0:
                root.append(chunk)

        # annotate chunks with metadata
        chunk_count = len(root)
        for i, chunk in enumerate(root):
            orig_id = chunk.get("id", fallback_orig_id)
            if orig_id is None:
                raise RuntimeWarning(
                    "Original structure has no @id attribute, the @id attributes "
                    "of groups under it might therefore not be unique. Specify a "
                    "``fallback_root_id`` to bypass the issue.")
            chunk.set(root.tag + "_id", orig_id)
            chunk.set("id", "{}_{}".format(orig_id, i))
            chunk.set("position_in_text", chunk_pos(i, chunk_count))

        return root

    def group(self, target, attr, as_struct, fallback_root_id=False):
        """Group target structures under the root according to attribute values.

        :param target: The structures to group.
        :param attr: Iterable of attributes by whose values to group them by.
        :param as_struct: The tag name to use for the groups.
        :param fallback_root_id: If structure has no @id attribute, this will
            be used instead to generate the @ids of the groups. If None, the
            @ids will consist solely of the grouping attributes and it is the
            user's responsibility to ensure they're unique.
        :rtype: etree.Element

        """
        root = etree.Element(self.xml.tag, attrib=self.xml.attrib)
        root.text = root.tail = "\n"
        root_id = root.get("id", fallback_root_id)
        if root_id is False:
            raise RuntimeWarning(
                "Parent structure has no @id attribute, the @id attributes of "
                "groups under it might therefore not be unique. Specify a "
                "``fallback_root_id`` to bypass the issue, or set it to None "
                "if uniqueness is ensured otherwise.")

        def new_group(attrib, id):
            g = etree.SubElement(root, as_struct, attrib=attrib)
            g.set("id", id)
            g.text = g.tail = "\n"
            return g

        groups = {}
        for target in self.xml.iter(target):
            t_val = tuple(target.get(a, None) for a in attr)
            id = ",".join(map(str, t_val))
            if fallback_root_id is not None:
                id = root_id + "/" + id
            if t_val not in groups:
                # new Python 3.5 syntax; in case of dupes, the last occurrence
                # of a key takes precedence:
                # attrib = {**root.attrib, **target.attrib}
                attrib = dict(root.attrib.items())
                attrib.update(target.attrib)
                group = groups.setdefault(t_val, new_group(attrib, id))
            else:
                group = groups.get(t_val)
            group.append(target)
        return root

    def project(self, child):
        """Project the root structure's metadata onto its children.

        The structure is *modified in place*.

        Projected attributes are prefixed with the parent structure's name, and
        if necessary, postfixed with underscores so as to avoid collisions with
        any existing attributes in the child structure.

        :param child: The child structure onto which to project.

        """
        attrib = self.xml.attrib
        for child in self.xml.iter(child):
            for key in attrib:
                ckey = self.name + "_" + key
                while ckey in child.attrib:
                    ckey += "_"
                if key not in child.attrib:
                    child.attrib[ckey] = attrib[key]

    def _xmlize(self):
        """Transform vertical into marginally valid XML.

        """
        # get rid of all XML entities and HTML entity references
        vert = unescape(self.raw)
        # escape only the bare minimum necessary for successful parsing as XML
        vert = re.sub(r"&", r"&amp;", vert)
        vert = re.sub(r"<", "&lt;", vert)
        vert = re.sub(r">", "&gt;", vert)
        # now put pointy brackets back where they belong (= only on lines which
        # we are reasonably sure are structure start / end tags)
        match = r"^&lt;(/?({})[^\t]*?)&gt;$".format("|".join(self.structs))
        vert = re.sub(match, r"<\1>", vert, flags=re.M)
        return vert


class ValidTags:
    """Keep track of valid tag names in a vertical file.

    """
    def __init__(self, start=None, end=None, void=None, structs=None):
        self.start = start if start else re.compile(r"<(\w+).*?(?<!/)>")
        self.end = end if end else re.compile(r"</(\w+)>")
        self.void = void if void else re.compile(r"<(\w+).*?/>")
        self.stags = set()
        self.etags = set()
        self.vtags = set()

    def add(self, line):
        s = self.start.fullmatch(line)
        e = self.end.fullmatch(line)
        v = self.void.fullmatch(line)
        if s:
            self.stags.add(s.group(1))
        elif e:
            self.etags.add(e.group(1))
        elif v:
            self.vtags.add(v.group(1))
        return bool(s or e or v)

    def resolve(self):
        return self.stags.intersection(self.etags).union(self.vtags)


class DummyValidTags:
    """Anamorphous to ValidTags but returns structs passed to constructor on
    self.resolve().

    """
    def __init__(self, structs):
        self.structs = structs

    def add(self, line):
        pass

    def resolve(self):
        return self.structs


def iterstruct(vert_file, struct=None, structs=None):
    """Yield input vertical one struct at a time.

    :param vert_file: Input vertical.
    :param struct: The name of the struct into which the vertical will be
        chopped. If None, the whole vertical is returned, wrapped in a
        ``<root/>`` element.
    :param structs: A set of tag names to be considered as valid nested
        structures under ``struct``. When in doubt, leave ``None`` (automatic
        discovery), otherwise those you missed might be XML-escaped.
    :rtype: Structure

    """
    # override structs with global STRUCTS if they aren't set (STRUCTS in turn
    # might not be set, in which case this is a no-op)
    if structs is None:
        structs = STRUCTS

    # if the whole input vertical is to be wrapped and structs were provided,
    # we can take a shortcut
    if struct is None and structs:
        structs.add("root")
        yield Structure("<root>\n" + vert_file.read().strip() + "\n</root>", structs)
        raise StopIteration
    # else, we'll just surround the vertical with <root/> tags and go the
    # regular way (line by line)
    elif struct is None:
        struct = "root"
        vert_file = chain(["<root>"], vert_file, ["</root>"])

    # NOTE: string concatenation inside a for-loop is supposedly slow in
    # python, but building and then joining lists was comparably slow (mostly
    # even slower); unless there's a point where it starts to make a big
    # difference (in terms of the number of concatenations / length of the list
    # required), there's no real incentive to change this code
    buffer = ""
    structs = DummyValidTags(structs) if structs else ValidTags()
    start = re.compile(r"<{}.*?>".format(struct))
    end = re.compile(r"</{}>".format(struct))
    for line in vert_file:
        line = line.strip()
        # if the buffer already contains something or if the current line
        # starts with the given structure name, then we're inside a target
        # structure that we want to collect; otherwise, just skip to the next
        # line
        if buffer or start.fullmatch(line):
            structs.add(line)
            buffer += line + "\n"
            if end.fullmatch(line):
                yield Structure(buffer, structs.resolve())
                # NOTE: it might be a good idea to reset structs to a new
                # ValidTags object at this point, if we truly want to allow for
                # the possibility that different structures in the same
                # vertical might allow different nested substructures; in
                # practice though, indexing tools like manatee have just one
                # set of valid tag names per vertical
                buffer = ""


def config(**kwargs):
    for k, v in kwargs.items():
        globals()[k.upper()] = v
