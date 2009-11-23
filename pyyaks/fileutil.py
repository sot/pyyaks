"""Pyyaks file utilities"""
import os
import tempfile
import shutil
import re
import shutil
import glob
import gzip
import logging

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

logger = logging.getLogger('pyyaks')
logger.addHandler(NullHandler())
logger.propagate = False

class TempDir(object):
    """Create a temporary directory that gets automatically removed.  Any
    object initialization parameters are passed through to `tempfile.mkdtemp`_.
    ::

      >>> import pyyaks.fileutil
      >>> tmpdir = pyyaks.fileutil.TempDir(dir='.')
      >>> tmpdir.name
      './tmpcCH_l-'
      >>> del tmpdir

    .. _tempfile.mkdtemp: http://docs.python.org/library/tempfile.html#tempfile.mkdtemp 
    """
    def __init__(self, *args, **kwargs):
        self.__dirname = tempfile.mkdtemp(*args, **kwargs)
        self.name = self.__dirname      # "public" attribute
        
    def __del__(self):
        """Remove the temp directory when the object is destroyed."""
        shutil.rmtree(self.__dirname)

def get_globfiles(fileglob, minfiles=1, maxfiles=1):
    """
    Get file(s) matching ``fileglob``.  If the number of matching
    files is less than minfiles or more than maxfiles then an
    exception is raised.

    :param fileglob: Input file glob
    :param minfiles: Minimum matching files (None => no minimum)
    :param maxfiles: Maximum matching files (None => no maximum)
    """
    files = glob.glob(fileglob)
    nfiles = len(files)
    if minfiles is not None and nfiles < minfiles:
        raise ValueError('At least %d file(s) required for %s but %d found' % (minfiles, fileglob, nfiles))
    if maxfiles is not None and nfiles > maxfiles:
        raise ValueError('No more than %d file(s) required for %s but %d found' % (maxfiles, fileglob, nfiles))

    return files
    
def relpath(path, cwd=None):
    """ Find relative path from current directory to path.

    Example usage::
    
      >>> from pyyaks.fileutil import relpath
      >>> relpath('/a/b/hello/there', cwd='/a/b/c/d')
      '../../hello/there'
      >>> relpath('/a/b/c/d/e/hello/there', cwd='/a/b/c/d')
      'e/hello/there'

      >>> # Special case - don't go up to root and back
      >>> relpath('/x/y/hello/there', cwd='/a/b/c/d')
      '/x/y/hello/there'

    :param path: Destination path
    :param cwd: Current directory (default: os.getcwd() )
    :rtype: Relative path

    """
    if cwd is None:
        cwd = os.getcwd()

    currpath = os.path.abspath(cwd)
    destpath = os.path.abspath(os.path.join(cwd, path))
    currpaths = currpath.split(os.sep)
    destpaths = destpath.split(os.sep)

    # Don't go up to root and back.  Since we split() on an abs path the
    # zero element is always ''
    if currpaths[1] != destpaths[1]:
        return destpath

    # Get rid of common path elements
    while currpaths and destpaths and currpaths[0] == destpaths[0]:
        currpaths.pop(0)
        destpaths.pop(0)

    # start with enough '..'s to get to top of common path then get
    # the rest of the destpaths.  Return '' if the list ends up being empty.
    relpaths = [os.pardir] * len(currpaths) + destpaths
    return os.path.join(*relpaths) if relpaths else ''

def make_local_copy(infile, outfile=None, copy=False, linkabs=False, clobber=True):
    """
    Make a local copy of or link to ``infile``, gunzipping if necessary.
    
    Examples::

      >>> import pyyaks.fileutil
      >>> import random, tempfile
      >>> a = os.linesep.join([str(random.random()) for i in range(100)])
      >>> tmpfile = tempfile.mkstemp()[1]
      >>> open(tmpfile, 'w').write(a)
      >>> stat = subprocess.Popen(['gzip', '--stdout', tmpfile], stdout=open(tmpfile+'.gz','w')).communicate()
      >>> tmplocal = pyyaks.fileutil.make_local_copy(tmpfile, clobber=True)
      >>> a == open(tmplocal).read()
      True
      >>> tmplocal = pyyaks.fileutil.make_local_copy(tmpfile+'.gz', clobber=True)
      >>> a == open(tmplocal).read()
      True
      >>> os.unlink(tmpfile)
      >>> os.unlink(tmplocal)

    :param infile: Input file name
    :param outfile: Output file name (default: ``infile`` basename)
    :param copy: Always copy instead of linking when possible
    :param linkabs: Create link to absolute path instead of relative
    :param clobber: Clobber existing file
    :rtype: Output file name

    """
    
    if not os.path.exists(infile):
        raise IOError('Input file %s not found' % infile)

    if not outfile:
        outfile = re.sub(r'\.gz$', '', os.path.basename(infile))

    if os.path.exists(outfile):
        if clobber:
            os.unlink(outfile)
        else:
            raise IOError('Output file %s already exists and clobber is not set' % outfile)

    if infile.endswith('.gz'):
        out = open(outfile, 'wb')
        f = gzip.open(infile)
        while True:
            # read up to 100 Mb at a time
            data = f.read(10000) # 0000
            if data:
                out.write(data)
            else:
                break
        out.close()
        f.close()
    elif copy:
        shutil.copy2(infile, outfile)
    else:                               # symbolic link
        infile_abs = os.path.abspath(infile)
        if linkabs:
            infile_link = infile_abs
        else:
            infile_link = relpath(infile_abs, cwd=os.path.dirname(outfile))
        os.symlink(infile_link, outfile)

    return outfile
    
