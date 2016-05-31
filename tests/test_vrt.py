#!/usr/bin/env python3

import pytest
from pyvert.vrt import vrt
from click.testing import CliRunner

import os

R = CliRunner()
ACCESSED = set()


class Fix:

    def __init__(self, rstrip=False):
        self._fix = {}
        self.fn = {}
        dirname = os.path.join(os.path.dirname(__file__), "resources")
        for fn in os.listdir(dirname):
            path = os.path.join(dirname, fn)
            with open(path) as fh:
                res = os.path.basename(fn)
                res = os.path.splitext(res)[0]
                text = fh.read()
                # variant where (only) input files have no final newline
                if rstrip and "_" not in res:
                    text = text.rstrip()
                self._fix[res] = text
                self.fn[res] = path

    def __getattr__(self, attr):
        ACCESSED.add(attr)
        return self._fix[attr]


def opt(args):
    # stderr needs to be silenced or else it's mixed with the output
    return ["-l", "WARNING"] + args.split()


def optf(f, args):
    return ["-l", "WARNING", "-i", f] + args.split()


@pytest.mark.parametrize("fix", [Fix(), Fix(True)])
def test_filter(fix):
    ans = R.invoke(vrt, opt("filter -s chunk -a author foo"),
                   input=fix.test1)
    assert ans.exit_code == 0
    assert ans.output == fix.test1_filter1

    ans = R.invoke(vrt, opt("filter -s chunk -a author foo"),
                   input=fix.test2)
    assert ans.exit_code == 0
    assert ans.output == fix.test2_filter1


@pytest.mark.parametrize("fix", [Fix(), Fix(True)])
def test_group(fix):
    ans = R.invoke(vrt, opt("group -t chunk -a author"),
                   input=fix.test1)
    assert ans.exit_code == 0
    assert ans.output == fix.test1_group1

    ans = R.invoke(vrt, opt("group -t chunk -a author"),
                   input=fix.test2)
    assert ans.exit_code == 0
    assert ans.output == fix.test2_group1

    ans = R.invoke(vrt, opt("group -t chunk -a author -p doc"),
                   input=fix.test1)
    assert ans.exit_code == 0
    assert ans.output == fix.test1_group2

    ans = R.invoke(vrt, opt("group -t chunk -a author -p doc"),
                   input=fix.test2)
    assert ans.exit_code == 0
    assert ans.output == fix.test2_group2


def test_unescape():
    ans = R.invoke(vrt, opt("unescape"), input="&amp;\n&lt;\n")
    assert ans.exit_code == 0
    assert ans.output == "&\n<\n"

    ans = R.invoke(vrt, opt("unescape"), input="&amp;\n&lt;")
    assert ans.exit_code == 0
    assert ans.output == "&\n<\n"

    ans = R.invoke(vrt, opt("unescape --no-recursive"), input="&amp;lt;")
    assert ans.exit_code == 0
    assert ans.output == "&lt;\n"

    ans = R.invoke(vrt, opt("unescape"), input="&amp;lt;")
    assert ans.exit_code == 0
    assert ans.output == "<\n"


@pytest.mark.parametrize("fix", [Fix(), Fix(True)])
def test_file_input_and_wrap(fix):
    ans = R.invoke(vrt, optf(fix.fn["test2"], "wrap -t chunk -a author"))
    # assert ans.exit_code == 0
    assert ans.output == fix.test2_wrap1

    ans = R.invoke(vrt, opt("wrap -t chunk -a author"), input=fix.test3)
    # assert ans.exit_code == 0
    assert ans.output == fix.test3_wrap1


def test_all_resources_were_accessed(fix=Fix()):
    assert set(fix._fix.keys()) == ACCESSED
