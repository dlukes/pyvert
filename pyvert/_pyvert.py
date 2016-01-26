from lazy import lazy
from tempfile import NamedTemporaryFile as NamedTempFile

import re
import random
from lxml import etree

__all__ = ["Structure", "iterstruct"]

__version__ = "0.0.0"

# disable security preventing DoS attacks with huge files
etree.set_default_parser(etree.ETCompatXMLParser(huge_tree=True))


class Structure():
    """A structure extracted from a vertical.

    """
    def __init__(self, raw_vert):
        self.raw = raw_vert
        self._first_line = self.raw.split("\n", maxsplit=1)[0]
        self.name = re.search(r"^<(\w+)", self._first_line)
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
        # DELETEME
        # debug = lambda: logging.debug(
        #     "Chunk: {} positions for a planned length of {} in {}."
        #     .format(positions, chunk_length, root.get("id")))
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
            # DELETEME
            # with open("postupne.txt", "a") as fh:
            #     print(text, file=fh)
            # set the child's text (remember, if it was a paragraph to start
            # with, it only had newlines in its text)
            new_child.text = "\n" + text + "\n"
            new_child.tail = child.tail
            if positions >= chunk_length:
                # DELETEME
                # foo = chunk.xpath("string()").strip("\n")
                # foo = re.sub(r"\n{2,}", "\n", foo)
                # with open("najednou.txt", "a") as fh:
                #     print(foo, file=fh)
                # foo = len(foo.splitlines())
                # logging.debug((foo, positions))
                # assert foo == positions
                # debug()
                root.append(chunk)
                chunk, chunk_length, positions = loop_vars(name, root.attrib, minmax)
        # after the for-loop ends, check if there's a final non-empty chunk
        # that didn't accumulate the required number of positions
        else:
            if positions > 0:
                # DELETEME
                # foo = chunk.xpath("string()").strip("\n")
                # foo = re.sub(r"\n{2,}", "\n", foo)
                # foo = len(foo.splitlines())
                # logging.debug((foo, positions))
                # debug()
                root.append(chunk)

        # annotate chunks with metadata
        chunk_count = len(root)
        for i, chunk in enumerate(root):
            orig_id = chunk.get("id", None)
            chunk.set(root.tag + "_id", orig_id)
            chunk.set("id", "{}_{}".format(orig_id, i))
            chunk.set("position_in_text", chunk_pos(i, chunk_count))

        return root

    def _xmlize(self):
        """Transform vertical into marginally valid XML.

        """
        vert = self.raw
        vert = re.sub(r"&", r"&amp;", vert)
        # anything that looks like a tag but is really a position (i.e. it's
        # followed at some point by a tab -- TODO this fails for corpora which
        # have only one positional attribute) must be neutralized into XML
        # entitites
        vert = re.sub(r"<(?=.*?\t)", r"&lt;", vert)
        vert = re.sub(r">(?=.*?\t)", r"&gt;", vert)
        return vert


def iterstruct(vert_file, struct="doc"):
    """Yield input vertical one struct at a time.

    :param vert_file: Input vertical.
    :param struct: The name of the struct into which the vertical will be
        chopped.
    :rtype: Structure

    """
    buffer = ""
    for line in vert_file:
        buffer += line
        if line.startswith("</{}".format(struct)):
            yield Structure(buffer)
            buffer = ""
