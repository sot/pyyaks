import os
import tempfile
import time
import pyyaks.context as context
import nose.tools as nt

SRC = context.ContextDict('src')
Src = SRC.accessor()
FILE = context.ContextDict('file', basedir='data')
File = FILE.accessor()
File['evt2'] = 'obs{{ src.obsid }}/{{src.nested}}/acis_evt2'

def test_set_by_key():
    SRC['obsid'] = 123
    SRC['srcdir'] = 'obs{{ src.obsid }}/{{src.nested}}'

def test_set_by_accessor_key():
    Src['ccdid'] = 2
    File['srcdir'] = '{{ src.srcdir }}'
    File['evt2']   = '{{ src.srcdir }}/acis_evt2'

def test_set_by_attr():
    Src.nested = 'nested{{src.ccdid}}'

def test_basic():
    assert str(SRC['obsid']) == '123'
    assert str(SRC['ccdid']) == '2'
    assert Src.obsid == 123
    assert Src['obsid'] == 123

def test_nested():
    assert str(SRC['srcdir']) == 'obs123/nested2'

def test_get_accessor():
    assert File['srcdir'] == 'data/obs123/nested2'

def test_get_attr():
    assert File.srcdir == 'data/obs123/nested2'

def test_auto_create():
    SRC['ra'].format = '%.2f'
    assert SRC['ra'].val is None
    assert SRC['ra'].mtime is None

def test_format():
    SRC['ra'] = 1.2343256789
    assert str(SRC['ra']) == '1.23'
    SRC['ra'].format = '%.4f'
    assert str(SRC['ra']) == '1.2343'

def test_file_rel():
    assert str(FILE['evt2']) == FILE['evt2'].rel
    assert str(FILE['evt2.fits']) == 'data/obs123/nested2/acis_evt2.fits'
    assert context.render('{{file.evt2.fits}}') == 'data/obs123/nested2/acis_evt2.fits'

def test_file_abs():
    assert FILE['evt2.fits'].abs == os.path.join(os.getcwd(), 'data/obs123/nested2/acis_evt2.fits')

@nt.raises(ValueError)
def test_dot_in_key():
    FILE['acis_evt2.fits'] = 'acis_evt2.fits'

def test_abs_file1():
    FILE['abs'] = '/usr/bin/env'
    assert FILE['abs'].rel == '/usr/bin/env'
    assert FILE['abs'].abs == '/usr/bin/env'
    
def test_abs_file2():
    FILE['abs'] = os.getcwd()
    assert FILE['abs'].rel == ''
    assert FILE['abs'].abs == os.getcwd()
    
def test_file_mtime():
    tmp = tempfile.NamedTemporaryFile()
    FILE['tmp'] = tmp.name
    dt = abs(FILE['tmp'].mtime - time.time())
    tmp.close()
    assert(dt < 2)

def test_var_mtime():
    assert(SRC['new'].mtime is None)
    SRC['new'] = 1.0
    assert(abs(SRC['new'].mtime - time.time()) < 2)
