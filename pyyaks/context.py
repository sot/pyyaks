import re
import os
import time
import stat
import pdb

import django.template
import django.conf
import Ska.File

Context = {}
Django_tag = re.compile(r'{[%{]')

try:
    django.conf.settings.configure()
except RuntimeError, msg:
    print msg
    pass

def render(s):
    """Convenience function to create an anonymous ContextValue and then render it."""
    if isinstance(s, Value):
        return str(s)
    else:
        return str(Value(s))

def render_first_arg(func):
    """Wrap func so that its first arg is rendered"""
    def newfunc(*args, **kwarg):
        newargs = list(args)
        if len(newargs) > 0:
            newargs[0] = render(newargs[0])
        return func(*newargs, **kwarg)
    
    newfunc.func_name = func.func_name
    newfunc.func_doc = func.func_doc
    return newfunc

def render_args(func):
    """Wrap func so that all args rendered"""
    def newfunc(*args, **kwarg):
        newargs = [render(x) for x in args]
        return func(*newargs, **kwarg)

    newfunc.func_name = func.func_name
    newfunc.func_doc = func.func_doc
    return newfunc

class Value(object):
    def __init__(self, val=None, name=None, basedir=None, format=None, ext=None):
        # Possibly inherit attrs (except for 'ext') from an existing Value object
        if isinstance(val, Value):
            for attr in ('_val', '_mtime', 'name', 'basedir', 'format'):
                setattr(self, attr, getattr(val, attr))
        else:
            self._val = val
            self._mtime = None if val is None else time.time()
            self.name = name
            self.format = format
            self.basedir = basedir and os.path.abspath(basedir)
            self.format = format

        self.ext = ext

    def getval(self):
        return self._val

    def setval(self, val):
        self._val = val
        self._mtime = time.time()

    val = property(getval, setval)

    @property
    def mtime(self):
        if self.basedir:
            filename = str(self)
            return (os.stat(filename)[stat.ST_MTIME] if os.path.exists(filename) else None)
        else:
            return self._mtime

    def __unicode__(self):
        return str(self)
    
    def __str__(self):
        # pdb.set_trace()
        val = self._val
        try:                            
            # Following line will give TypeError unless val is string-like
            while (Django_tag.search(val)):
                template = django.template.Template(val)
                context = django.template.Context(Context)
                strval = template.render(context)
                if strval == val:
                    break
                else:
                    val = strval
        except TypeError:
            strval = (self.format or '%s') % val

        if self.basedir:
            if not os.path.isabs(strval):
                strval = os.path.join(self.basedir, strval)
            strval = Ska.File.relpath(strval + ('.' + self.ext if self.ext else ''))

        return strval

    @property
    def rel(self):
        return str(self)

    @property
    def abs(self):
        return os.path.abspath(str(self))

    def __getattr__(self, ext):
        """Any unfound attribute lookup is interpreted as a file extension.
        A new Value object with that extension is returned.
        """
        return Value(val=self, ext=ext)

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
    def __init__(self, name, basedir=None):
        dict.__init__(self)
        Context[name] = self
        self.name = name
        self.basedir = basedir

    def __getitem__(self, key):
        """Get key value from the ContextDict.  For a ContextDict with valuetype==File
        then allow for extensions on key.
        """
        match = re.match(r'([^.]+)\.(.+)', key)
        base, ext = match.groups() if match else (key, None)

        # Autogenerate an entry for key
        if base not in self:
            dict.__setitem__(self, base, Value(val=None, name=base, basedir=basedir))

        baseValue = dict.__getitem__(self, base)
        return (Value(baseValue, ext=ext) if ext else baseValue)

    def __setitem__(self, key, val):
        # If ContextValue was already init'd then just update val
        if key in self:
            dict.__getitem__(self, key).val = val
        else:
            dict.__setitem__(self, key, Value(val=val, name=key, basedir=self.basedir))

    def update(self, vals):
        if hasattr(vals, 'items'):
            vals = vals.items()
        for key, val in vals:
            self[key] = val

    def accessor(self):
        return ContextDictAccessor(self)

    def __repr__(self):
        return str(dict((key, self[key].val) for key in self))

class ContextDictAccessor(object):
    """Very simple mechanism to access ContextDict values via object attribute
    syntax.  For a ContextValue.Value object the value is returned.
    For a ContextValue.File object the relative path name is returned.

    Example::

      SRC = ContextDict('src')
      Src = Src.accessor()
      SRC['test'] = 5.2
      Src.test
      Src.test = 8
      SRC['test'].val
      FileDict = ContextDict('file', basedir='/pool14', valuetype=ContextValue.File)
      File = ContextDictAccessor(FileDict)
      File.obs_dir = 'obs{{src.obsid}} /'
      File.obs_dir
    """
    def __init__(self, contextdict):
        object.__setattr__(self, '_contextdict', contextdict)

    def __getattr__(self, name):
        try:
            return self._contextdict[name].rel
        except AttributeError:
            return self._contextdict[name].val

    def __setattr__(self, name, value):
        self._contextdict[name] = value
        
    def __getitem__(self, name):
        return self.__getattr__(name)
    
    def __setitem__(self, name, value):
        self.__setattr__(name, value)

