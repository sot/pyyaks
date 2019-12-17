# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import print_function

import ska_helpers


def test(*args, **kwargs):
    '''
    Run py.test unit tests.
    '''
    import testr
    return testr.test(*args, **kwargs)

__version__ = ska_helpers.get_version(__package__)
