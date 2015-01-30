from __future__ import print_function, division, absolute_import

import os
import tempfile
import time
from .. import logger as pyyaks_logger
from .. import context
import pytest

from six.moves import cPickle as pickle

logger = pyyaks_logger.get_logger()

src = context.ContextDict('src')
files = context.ContextDict('files', basedir='pyyaks:data')

def test_format_filter():
    src['obsid'] = 123
    src['test_format'] = '{{ "%05d"|format(src.obsid.val) }}'
    assert str(src['test_format']) == '00123'
    
def test_set_by_key():
    src['obsid'] = 123
    src['srcdir'] = 'obs{{ src.obsid }}/{{src.nested}}'

def test_set_by_accessor_key():
    src.val['ccdid'] = 2
    files.val['srcdir'] = '{{ src.srcdir }}'
    files.val['evt2']   = '{{ src.srcdir }}/acis_evt2'

def test_set_by_attr():
    src.val.nested = 'nested{{src.ccdid}}'

def test_basic():
    assert str(src['obsid']) == '123'
    assert str(src['ccdid']) == '2'
    assert src.val.obsid == 123
    assert src.val['obsid'] == 123
    assert src['obsid'].val == 123

def test_nested():
    assert str(src['srcdir']) == 'obs123/nested2'

def test_get_accessor():
    assert files.rel['srcdir'] == 'data/obs123/nested2'

def test_get_attr():
    assert files.rel.srcdir == 'data/obs123/nested2'

def test_auto_create():
    src['ra'].format = '%.2f'
    assert src['ra'].val is None
    assert src['ra'].mtime is None

def test_format():
    src['ra'] = 1.2343256789
    assert str(src['ra']) == '1.23'
    src['ra'].format = '%.4f'
    assert str(src['ra']) == '1.2343'

def test_file_rel():
    assert str(files['evt2']) == files['evt2'].rel
    assert str(files['evt2.fits']) == 'data/obs123/nested2/acis_evt2.fits'
    assert context.render('{{files.evt2.fits}}') == 'data/obs123/nested2/acis_evt2.fits'

def test_file_abs():
    assert files['evt2.fits'].abs == os.path.join(os.getcwd(), 'data/obs123/nested2/acis_evt2.fits')

def test_multiple_basedir_paths():
    files['context'] = 'context'
    assert files['context.py'].rel == 'pyyaks/context.py'
    assert files['context.py'].abs == os.path.join(os.getcwd(), 'pyyaks/context.py')
    assert files['evt2.fits'].rel == 'data/obs123/nested2/acis_evt2.fits'    

def test_dot_in_key():
    with pytest.raises(ValueError):
        files['acis_evt2.fits'] = 'acis_evt2.fits'

def test_abs_file1():
    files['abs'] = '/usr/bin/env'
    assert files['abs'].rel == '/usr/bin/env'
    assert files['abs'].abs == '/usr/bin/env'
    
def test_abs_file2():
    files['abs'] = os.getcwd()
    assert files['abs'].rel == ''
    assert files['abs'].abs == os.getcwd()
    
def test_file_mtime():
    tmp = tempfile.NamedTemporaryFile()
    files['tmp'] = tmp.name
    dt = abs(files['tmp'].mtime - time.time())
    tmp.close()
    assert(dt < 2)

def test_var_mtime():
    assert(src['new'].mtime is None)
    src['new'] = 1.0
    assert(abs(src['new'].mtime - time.time()) < 2)

def test_store_update_context():
    src.val.nested = 'nested{{src.ccdid}}'
    src.val['ccdid'] = 2
    src['srcdir'] = 'obs{{ src.obsid }}/{{src.nested}}'
    files['srcdir'] = '{{ src.srcdir }}'
    src['obsid'] = 123
    src.val['ccdid'] = 2
    src['ra'] = 1.4343256789
    src['ra'].format = '%.4f'
    files['evt2'] = 'obs{{ src.obsid }}/{{src.nested}}/acis_evt2'
    src.val.nested = 'nested{{src.ccdid}}'

    tmp = pickle.dumps(src)
    tmp2 = pickle.dumps(files)

    src.clear()
    files.clear()

    assert src['ra'].val is None
    assert files['evt2'].val is None

    src.update(pickle.loads(tmp))
    files.update(pickle.loads(tmp2))

    assert str(src['ra']) == '1.4343'
    assert str(src['srcdir']) == 'obs123/nested2'
    assert files['srcdir'].rel == 'data/obs123/nested2'
    assert files.rel.srcdir == 'data/obs123/nested2'
    assert str(files['evt2.fits']) == 'data/obs123/nested2/acis_evt2.fits'
    
def test_update_basedir():
    files['tmpfile'] = 'tmpfile'
    a = files['tmpfile']
    assert files['tmpfile'].rel == 'data/tmpfile'
    files.basedir = 'newdata'
    assert files['tmpfile'].rel == 'newdata/tmpfile'
    assert a.rel == 'newdata/tmpfile'
    files.basedir = 'data'
    assert files['tmpfile'].rel == 'data/tmpfile'


def test_context_cache():
    """
    Test caching a ContextDict with a context manager.
    """
    def change1():
        with CM:
            CM['i'] = 20
            assert CM['i'].val == 20

    def change2():
        with CM:
            CM['i'] = 30
            assert CM['i'].val == 30
            change1()
            assert CM['i'].val == 30

    CM = context.ContextDict('c')
    CM['i'] = 10
    assert CM['i'].val == 10
    assert len(CM._context_manager_cache) == 0

    change2()

    assert CM['i'].val == 10
    assert len(CM._context_manager_cache) == 0


def test_context_cache_exception():
    """
    Test caching a ContextDict with a context manager.  Make sure that everything
    still works with an exception raised in the middle of nested calls.
    """
    def change1():
        with CM:
            CM['i'] = 20
            assert CM['i'].val == 20
            raise Exception

    def change2():
        with CM:
            CM['i'] = 30
            assert CM['i'].val == 30
            change1()
            assert CM['i'].val == 30

    CM = context.ContextDict('c')
    CM['i'] = 10
    assert CM['i'].val == 10
    assert len(CM._context_manager_cache) == 0

    try:
        change2()
    except:
        pass
    else:
        raise Exception('Embedded exception not raised')

    assert CM['i'].val == 10
    assert len(CM._context_manager_cache) == 0


def test_decorator_cache():
    """
    Test caching a ContextDict with a decorator.
    """
    CM = context.ContextDict('c')

    @CM.cache
    def change1():
        "Doc string"
        CM['i'] = 20
        assert CM['i'].val == 20

    @CM.cache
    def change2():
        CM['i'] = 30
        assert CM['i'].val == 30
        change1()
        assert CM['i'].val == 30

    assert change1.__name__ == 'change1'
    assert change1.__doc__ == 'Doc string'

    CM['i'] = 10
    assert CM['i'].val == 10

    change2()

    assert CM['i'].val == 10


def test_decorator_cache_exception():
    """
    Test caching a ContextDict with a decorator.  Make sure that everything
    still works with an exception raised in the middle of nested calls.
    """
    CM = context.ContextDict('c')

    @CM.cache
    def change1():
        CM['i'] = 20
        assert CM['i'].val == 20
        raise Exception

    @CM.cache
    def change2():
        CM['i'] = 30
        assert CM['i'].val == 30
        change1()
        assert CM['i'].val == 30

    CM['i'] = 10
    assert CM['i'].val == 10

    try:
        change2()
    except:
        pass
    else:
        raise Exception('Embedded exception not raised')

    assert CM['i'].val == 10


def test_reuse_context_dict():
    """
    Test that getting a ContextDict twice gives the same value.
    """
    c = context.ContextDict('c')
    c2 = context.ContextDict('c')
    assert c is c2
    c['a'] = 1
    assert c2['a'].val == 1


def test_reuse_context_dict_fail():
    """
    Test that getting a ContextDict twice but with different basedir fails.
    """
    c = context.ContextDict('c1')
    with pytest.raises(ValueError) as err:
        context.ContextDict('c1', basedir='something')
    assert 'ValueError: Re-using' in str(err)
