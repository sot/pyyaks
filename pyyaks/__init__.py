from __future__ import print_function

def test(*args, **kwargs):
    import os
    import pytest
    pkg_path = os.path.dirname(os.path.abspath(__file__))
    pkg_rootdir, pkg_name = os.path.split(pkg_path)
    os.chdir(pkg_rootdir)
    args = (pkg_name,) + args
    print(pkg_rootdir, pkg_name)
    pytest.main(list(args), **kwargs)

__version__ = '3.3.3'
