import os
from pypy.translator.translator import TranslationContext, graphof
from pypy.translator.unsimplify import (split_block, call_final_function,
     remove_double_links, no_links_to_startblock, call_initial_function)
from pypy.rpython.llinterp import LLInterpreter
from pypy.objspace.flow.model import checkgraph
from pypy.rlib.objectmodel import we_are_translated
from pypy.tool.udir import udir

def translate(func, argtypes, type_system="lltype"):
    t = TranslationContext()
    t.buildannotator().build_types(func, argtypes)
    t.entry_point_graph = graphof(t, func)
    t.buildrtyper(type_system=type_system).specialize()
    return graphof(t, func), t

def test_split_blocks_simple():
    for i in range(4):
        def f(x, y):
            z = x + y
            w = x * y
            return z + w
        graph, t = translate(f, [int, int])
        split_block(t.annotator, graph.startblock, i)
        checkgraph(graph)
        interp = LLInterpreter(t.rtyper)
        result = interp.eval_graph(graph, [1, 2])
        assert result == 5
    
def test_split_blocks_conditional():
    for i in range(3):
        def f(x, y):
            if x + 12:
                return y + 1
            else:
                return y + 2
        graph, t = translate(f, [int, int])
        split_block(t.annotator, graph.startblock, i)
        checkgraph(graph)
        interp = LLInterpreter(t.rtyper)
        result = interp.eval_graph(graph, [-12, 2])
        assert result == 4
        result = interp.eval_graph(graph, [0, 2])
        assert result == 3

def test_split_block_exceptions():
    for i in range(2):
        def raises(x):
            if x == 1:
                raise ValueError
            elif x == 2:
                raise KeyError
            return x
        def catches(x):
            try:
                y = x + 1
                raises(y)
            except ValueError:
                return 0
            except KeyError:
                return 1
            return x
        graph, t = translate(catches, [int])
        split_block(t.annotator, graph.startblock, i)
        checkgraph(graph)
        interp = LLInterpreter(t.rtyper)
        result = interp.eval_graph(graph, [0])
        assert result == 0
        result = interp.eval_graph(graph, [1])
        assert result == 1
        result = interp.eval_graph(graph, [2])
        assert result == 2

def test_remove_double_links():
    def f(b):
        return not b
    graph, t = translate(f, [bool])

    blocks = list(graph.iterblocks())
    assert len(blocks) == 2
    assert len(blocks[0].exits) == 2
    assert blocks[0].exits[0].target == blocks[1]
    assert blocks[0].exits[1].target == blocks[1]

    remove_double_links(t.annotator, graph)

    blocks = list(graph.iterblocks())
    assert len(blocks) == 3
    assert len(blocks[0].exits) == 2
    assert blocks[0].exits[0].target == blocks[1]
    assert blocks[0].exits[1].target == blocks[2]
    assert len(blocks[2].exits) == 1
    assert blocks[2].exits[0].target == blocks[1]

    checkgraph(graph)
    interp = LLInterpreter(t.rtyper)
    result = interp.eval_graph(graph, [True])
    assert result == False
    result = interp.eval_graph(graph, [False])
    assert result == True

def test_no_links_to_startblock():
    def f(b, x):
        while b > 0:
            x += 1
            b -= 1
        return x
    graph, t = translate(f, [int, int])

    assert not graph.startblock.operations
    graph.startblock = graph.startblock.exits[0].target
    assert graph.startblock.operations
    checkgraph(graph)
    interp = LLInterpreter(t.rtyper)
    result = interp.eval_graph(graph, [11, 0])
    assert result == 11

    assert graph.startblock.operations
    no_links_to_startblock(graph)
    assert not graph.startblock.operations
    checkgraph(graph)
    interp = LLInterpreter(t.rtyper)
    result = interp.eval_graph(graph, [11, 0])
    assert result == 11

def test_call_initial_function():
    tmpfile = str(udir.join('test_call_initial_function'))
    for type_system in ['lltype', 'ootype']:
        def f(x):
            return x * 6
        def hello_world():
            if we_are_translated():
                fd = os.open(tmpfile, os.O_WRONLY | os.O_CREAT, 0644)
                os.close(fd)
        graph, t = translate(f, [int], type_system)
        call_initial_function(t, hello_world)
        #
        if os.path.exists(tmpfile):
            os.unlink(tmpfile)
        interp = LLInterpreter(t.rtyper)
        result = interp.eval_graph(graph, [7])
        assert result == 42
        assert os.path.isfile(tmpfile)

def test_call_final_function():
    tmpfile = str(udir.join('test_call_final_function'))
    for type_system in ['lltype', 'ootype']:
        def f(x):
            return x * 6
        def goodbye_world():
            if we_are_translated():
                fd = os.open(tmpfile, os.O_WRONLY | os.O_CREAT, 0644)
                os.close(fd)
        graph, t = translate(f, [int], type_system)
        call_final_function(t, goodbye_world)
        #
        if os.path.exists(tmpfile):
            os.unlink(tmpfile)
        interp = LLInterpreter(t.rtyper)
        result = interp.eval_graph(graph, [7])
        assert result == 42
        assert os.path.isfile(tmpfile)
