# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import print_function


def test(*args, **kwargs):
    '''
    Run py.test unit tests.
    '''
    import testr
    return testr.test(*args, **kwargs)

__version__ = '3.3.5'
