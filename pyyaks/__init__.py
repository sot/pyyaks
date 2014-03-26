__version__ = '0.3.2'


def test(*args, **kwargs):
    import os
    import pytest
    pkg_path = os.path.dirname(os.path.abspath(__file__))
    pkg_rootdir, pkg_name = os.path.split(pkg_path)
    os.chdir(pkg_rootdir)
    args = (pkg_name,) + args
    print pkg_rootdir, pkg_name
    pytest.main(list(args), **kwargs)
