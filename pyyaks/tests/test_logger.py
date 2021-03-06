# Licensed under a 3-clause BSD style license - see LICENSE.rst
from __future__ import print_function, division, absolute_import

import tempfile
import os
from .. import logger as pyyaks_logger
import six

def test_suppress_newline():
    stdout = six.StringIO()
    logger = pyyaks_logger.get_logger(level=pyyaks_logger.INFO, stream=stdout)
    for handler in logger.handlers:
        handler.suppress_newline = True
    logger.info('Info')
    logger.warning('Warning')
    for handler in logger.handlers:
        handler.suppress_newline = False
    logger.info('Info')
    logger.warning('Warning')
    assert stdout.getvalue() == "InfoWarningInfo\nWarning\n"

def test_suppress_newline_cm():
    stdout = six.StringIO()
    logger = pyyaks_logger.get_logger(level=pyyaks_logger.INFO, stream=stdout)
    with pyyaks_logger.newlines_suppressed(logger):
        logger.info('Info')
        logger.warning('Warning')
    logger.info('Info')
    logger.warning('Warning')
    assert stdout.getvalue() == "InfoWarningInfo\nWarning\n"

def test_stream():
    stdout = six.StringIO()
    logger = pyyaks_logger.get_logger(level=pyyaks_logger.INFO, stream=stdout)
    logger.debug('Debug')
    logger.info('Info')
    logger.warning('Warning')
    assert stdout.getvalue() == "Info\nWarning\n"

def test_file(tmpdir):
    tmp = os.path.join(tmpdir, 'tmp.log')
    logger = pyyaks_logger.get_logger(filename=tmp, stream=None)
    logger.debug('Debug')
    logger.info('Info')
    logger.warning('Warning')
    assert open(tmp).read() == "Info\nWarning\n"

def test_redefine(tmpdir):
    stdout1 = six.StringIO()
    stdout2 = six.StringIO()
    tmp1 = os.path.join(tmpdir, 'tmp1.log')
    tmp2 = os.path.join(tmpdir, 'tmp2.log')
    logger = pyyaks_logger.get_logger(filename=tmp1, stream=stdout1, filelevel=pyyaks_logger.WARNING)
    logger.debug('Debug1')
    logger.info('Info1')
    logger.warning('Warning1')
    logger = pyyaks_logger.get_logger(filename=tmp2, stream=stdout2, level=pyyaks_logger.DEBUG)
    logger.debug('Debug2')
    logger.info('Info2')
    logger.warning('Warning2')
    assert open(tmp1).read() == "Warning1\n"
    assert stdout1.getvalue() == "Info1\nWarning1\n"
    assert open(tmp2).read() == "Debug2\nInfo2\nWarning2\n"
    assert stdout2.getvalue() == "Debug2\nInfo2\nWarning2\n"
