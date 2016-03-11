from os import environ as env
from lazy import lazy
from tempfile import NamedTemporaryFile as NamedTempFile
import logging
import click

import re
import random
from lxml import etree
from html import unescape

__all__ = ["Structure", "iterstruct"]

__version__ = "0.0.0"

# disable security preventing DoS attacks with huge files
etree.set_default_parser(etree.ETCompatXMLParser(huge_tree=True))

# valid structure (i.e. pseudo-XML tag) names
STRUCTURES = ["opus", "doc", "sp", "seg", "s", "text", "p", "hi", "lb",
              "group", "chunk"]


class Structure():
    """A structure extracted from a vertical.

    """
    def __init__(self, raw_vert, structs=env.get("VRT_STRUCTS", "").split()):
        """__init__

        :param structs: A list of strings to be considered valid struct
            names for substructures, in addition to STRUCTURES.

        """
        self.raw = raw_vert
        self.structs = set(STRUCTURES + structs)
        self._first_line = self.raw.split("\n", maxsplit=1)[0]
        self.name = re.findall(r"\w+", self._first_line)[0]
        self.attr = dict(re.findall(r'(\w+)="([^"]+)"', self._first_line))

    @lazy
    def xml(self):
        """The structure represented as an ElementTree.

        """
        xml = self._xmlize()
        try:
            return etree.fromstring(xml)
        except etree.XMLSyntaxError as e:
            with NamedTempFile(mode="w", suffix=".xml", delete=False) as fh:
                fh.write(xml)
            e = str(e)
            e += "\nAn XMLSyntaxError occurred while processing a document. " \
                 "It has been dumped to {} for inspection.".format(fh.name)
            raise Exception(e)

    def chunk(self, child, name, minmax):
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
        root.text = "\n"

        def loop_vars(name, attrib, minmax):
            chunk = etree.Element(name, attrib=attrib)
            chunk.text = "\n"
            chunk.tail = "\n"
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
            orig_id = chunk.get("id", None)
            chunk.set(root.tag + "_id", orig_id)
            chunk.set("id", "{}_{}".format(orig_id, i))
            chunk.set("position_in_text", chunk_pos(i, chunk_count))

        return root

    def group(self, target, attr, as_struct, fallback_root_id=None):
        """Group target structures under the root according to attribute values.

        :param target: The structures to group.
        :param attr: Iterable of attributes by whose values to group them by.
        :param as_struct: The tag name to use for the groups.
        :rtype: etree.Element

        """
        root = etree.Element(self.xml.tag, attrib=self.xml.attrib)
        root.text = "\n"
        root_id = root.get("id", fallback_root_id)
        if root_id is None:
            raise RuntimeWarning(
                "Parent structure has no @id attribute, the @id attributes of "
                "groups under it might therefore not be unique. Specify a "
                "``fallback_root_id`` to bypass the issue.")

        def new_group(attrib, id):
            g = etree.SubElement(root, as_struct, attrib=attrib)
            g.set("id", id)
            g.text = g.tail = "\n"
            return g

        groups = {}
        for target in self.xml.iter(target):
            t_val = tuple(target.get(a, None) for a in attr)
            id = root_id + "/" + ",".join(t_val)
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
        # warn about parts of the string which look a hell of a lot like
        # structures but have been escaped because they're not in the set of
        # valid structure names
        cx = click.get_current_context()
        command = cx.command.name if cx else ""
        for suspect in re.findall(
                r"""
                ^   &lt;   (\w+)   .*?   &gt;   $
                .*?
                ^   &lt;   /  \1   .*?   &gt;   $""",
                vert, flags=re.M | re.S | re.X):
            logging.warn(
                "Angle brackets around '{}' have been escaped, but it looks "
                "like it might be a structure. Consider adding it to the "
                "``VRT_STRUCTURES`` environment variable.".format(suspect),
                extra=dict(command=command))
        return vert


def iterstruct(vert_file, struct=None):
    """Yield input vertical one struct at a time.

    :param vert_file: Input vertical.
    :param struct: The name of the struct into which the vertical will be
        chopped. If None, the whole vertical is returned.
    :rtype: Structure

    """
    if struct is None:
        yield Structure(vert_file.read())
        raise StopIteration
    buffer = ""
    for line in vert_file:
        # if the buffer already contains something or if the current line
        # starts with the given structure name, then we're inside a target
        # structure that we want to collect; otherwise, just skip to the next
        # line
        if not (buffer or line.startswith("<{}".format(struct))):
            continue
        buffer += line
        if line.startswith("</{}".format(struct)):
            yield Structure(buffer)
            buffer = ""
