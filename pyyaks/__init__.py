__version__ = '0.3.1'


def test(*args, **kwargs):
    from . import tests
    tests.test(*args, **kwargs)
