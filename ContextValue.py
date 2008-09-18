import django.template
import django.conf
import re
import os

Context = {}

try:
    django.conf.settings.configure()
except RuntimeError, msg:
    print msg
    pass

def render(s):
    """Convenience function to create an anonymous ContextValue and then render it."""
    x = ContextValue(s)
    return str(x)

def render_func(func):
    """Wrap func so that its first arg is rendered"""
    def newfunc(*arg, **kwarg):
        newarg = list(arg)
        try:
            newarg[0] = render(newarg[0])
        except IndexError:
            pass
        return func(*newarg, **kwarg)
    return newfunc

def _relative_path(path, basedir=None, currdir=None):
    """ Find relative path from current directory to desired path.  E.g.
    currpath = /a/b/c/d
    destpath = /a/b/hello/there
    rel = ../../hello/there

    destpath = /a/b/c/d/e/hello/there
    rel = e/hello/there

    Special case (don't go up to root):
    destpath = /x/y/z
    rel = /x/y/z

    """
    if currdir is None:
        currdir = os.curdir
    if basedir is None:
        basedir = currdir

    currpath = os.path.abspath(currdir)
    destpath = os.path.abspath(os.path.join(basedir, path))
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
    # the rest of the destpaths
    relpaths = [os.pardir] * len(currpaths) + destpaths
    return os.path.join(*relpaths)

class ContextDict(dict):
    """Dictionary class that automatically registers the dict in the Context and
    overrides __setitem__ to create an appropriate ContextValue when assigning
    to a dict key.  Example:

    src = ContextDict('src')  # Make Context dict with root name 'src'
    src['obsid'] = 123
    files = ContextDict('file') # Context dict with root name 'file'
    files['src']  = 'data/obs{{ src.obsid }}'
    files['evt2'] = '{{ file.src }}/acis_evt2.fits'
    """
    def __init__(self, name, **kwargs):
        dict.__init__(self)
        Context[name] = self
        self.name = name
        self.kwargs = kwargs 

    def __setitem__(self, key, val):
        if isinstance(val, ContextValue):
            dict.__setitem__(self, key, val)
        else:
            # If ContextValue was already init'd then just update val
            if key in self:
                dict.__getitem__(self, key).val = val
            else:
                dict.__setitem__(self, key, ContextValue(val, key, **self.kwargs))

class ContextValue(object):
    def getval(self): return self.__val
    def setval(self, x):
        self.__val = x
        try:
            self.template = django.template.Template(x + '')
        except TypeError:
            self.template = None
    val = property(getval, setval)

    def __init__(self, val=None, name=None, format=None, basedir=None):
        if isinstance(val, ContextValue):
            self = val
            return
        
        self.format = format
        self.name = name
        if name:
            # Add to Context.  Some error checking here would be good
            # if e.g. name=var.subvar and var exists already but is not dict
            names = name.split('.')
            vc = Context
            for name in names[:-1]:
                if name not in vc:
                    vc[name] = {}
                vc = vc[name]
            vc[names[-1]] = self
        self.val = val
        self.basedir = basedir and os.path.abspath(basedir) or None

    def __unicode__(self):
        return str(self)

    def __str__(self):
        if self.template:
            django_context = django.template.Context(Context)
            val = self.template.render(django_context)
            while (re.search(r'{[%{]', val)):
                newval = django.template.Template(val).render(django_context)
                if newval == val:
                    break
                else:
                    val = newval
        else:
            val = self.val
                
        if self.format:
            strval = self.format % val
        else:
            strval = str(val)

        # If basedir is defined then this is a file so render as a relative path
        if self.basedir:
            strval = _relative_path(strval, basedir=self.basedir)

        return strval

    def getrel(self):
        return str(self)

    def getabs(self):
        # First get the path but without automatic relative path translation
        path = render(self.val)
        if os.path.isabs(path):
            return path
        else:
            return os.path.join(self.basedir, path)

    rel = property(getrel)
    abs = property(getabs)

