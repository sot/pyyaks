from __future__ import print_function, division, absolute_import

import os
from .. import context

SR = context.ContextDict('sr')
SR['a'] = 'a'
SR['b'] = 'b'
SR['c'] = 'c'

@context.render_args()
def func1(arg1, arg2, arg3):
    """Doc string"""
    return arg1, arg2, arg3

@context.render_args(1)
def func2(arg1, arg2, arg3):
    return arg1, arg2, arg3

@context.render_args(1, 3)
def func3(arg1, arg2, arg3):
    return arg1, arg2, arg3

@context.render_args(1, 3, 2)
def func4(arg1, arg2, arg3):
    return arg1, arg2, arg3

@context.render_args(1, 3, 2)
def func5(val=None):
    return val

def test_render1():
    assert func1('{{sr.a}}', '{{sr.b}}', '{{sr.c}}') == ('a', 'b', 'c')
    assert func1.__name__ == 'func1'
    assert func1.__doc__ == 'Doc string'

def test_render2():
    assert func2('{{sr.a}}', '{{sr.b}}', '{{sr.c}}') == ('a', '{{sr.b}}', '{{sr.c}}')

def test_render3():
    assert func3('{{sr.a}}', '{{sr.b}}', '{{sr.c}}') == ('a', '{{sr.b}}', 'c')

def test_render4():
    assert func4('{{sr.a}}', '{{sr.b}}', '{{sr.c}}') == ('a', 'b', 'c')

def test_render5():
    assert func5(val='{{sr.a}}') == '{{sr.a}}'
