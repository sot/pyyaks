import re
import os
import time
import stat

import django.template
import django.conf
import Ska.File

Context = {}

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
    def __init__(self, val=None, name=None):
        self.val = val
        self.name = name
        self._mtime = None if val is None else time.time()
        self._format = None

    def getval(self):
        return self.__val

    def setval(self, val):
        self.__val = val
        try:
            self.template = django.template.Template(val + '')
        except TypeError:
            self.template = None
        self._mtime = time.time()

    val = property(getval, setval)

    @property
    def mtime(self):
        return self._mtime

    def __unicode__(self):
        return str(self)
    
    def __str__(self):
        if self.template is not None:
            django_context = django.template.Context(Context)
            val = self.template.render(django_context)
            while (re.search(r'{[%{]', val)):
                newval = django.template.Template(val).render(django_context)
                if newval == val:
                    break
                else:
                    val = newval
        else:
            if self._format:
                val = self._format % self.val
            else:
                val = str(self.val)
        return val

class File(Value):
    def __init__(self, val, name=None, basedir=None):
        # First initialize as a regular Value, but strip spaces for convenience
        try:
            val = re.sub(' ', '', val)
        except:
            pass
        super(File, self).__init__(val, name)
        self.basedir = (os.getcwd() if basedir is None else os.path.abspath(basedir))

    def __str__(self):
        """Return rendered object value as a path relative to cwd.  The
        value is taken as a path relative to self.basedir."""
        
        # Generate filepath as rendered object val relative to basedir.
        # Note that os.path.join(p1,p2) will ignore p1 if p2 is absolute.
        filepath = os.path.join(self.basedir, super(File, self).__str__())
        return Ska.File.relpath(filepath)

    def getrel(self):
        return str(self)

    def getabs(self):
        # First get the path but without automatic relative path translation
        path = render(self.val)
        if os.path.isabs(path):
            return path
        else:
            return os.path.join(self.basedir, path)

    def __getattr__(self, ext):
        """Any unfound attribute lookup is interpreted as a file extension.
        A new File object with that extension is returned.
        """
        return File(val=self.val + '.' + ext, name=self.name, basedir=self.basedir)

    rel = property(getrel)
    abs = property(getabs)

    @property
    def mtime(self):
        filename = render(self.val)
        return (os.stat(filename)[stat.ST_MTIME] if os.path.exists(filename) else None)

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
    def __init__(self, name, valuetype=Value, **kwargs):
        dict.__init__(self)
        Context[name] = self
        self.name = name
        self.valuetype = valuetype
        self.kwargs = kwargs
        self.format = dict()

    def __getitem__(self, key):
        """Get key value from the ContextDict.  For a ContextDict with valuetype==File
        then allow for extensions on key.
        """
        # If the key is not found then look for an extension and try again without the extension
        if self.valuetype == File:
            match = re.match(r'([^.]+)(\..+)', key)
            base, ext = match.groups() if match else (key, '')
            if base not in self:
                dict.__setitem__(self, base, File(val=None, name=base, **self.kwargs))
                
            baseFile = dict.__getitem__(self, base)
            return File(val=baseFile.val + ext, name=baseFile.name, basedir=baseFile.basedir)
            
        if key not in self and self.valuetype == File:
            try:
                base, ext = re.match(r'([^.]+)(\..+)', key).groups()
                baseFile = dict.__getitem__(self, base)
                return File(val=baseFile.val + ext, name=baseFile.name, basedir=baseFile.basedir)
            except:
                # If any of the above didn't work then fall through and raise KeyError exception
                # below using original key
                pass

        return dict.__getitem__(self, key)

    def __setitem__(self, key, val):
        if isinstance(val, self.valuetype):
            dict.__setitem__(self, key, val)
        else:
            # If ContextValue was already init'd then just update val
            if key in self:
                dict.__getitem__(self, key).val = val
            else:
                dict.__setitem__(self, key, self.valuetype(val, key, **self.kwargs))
                if key in self.format:
                    dict.__getitem__(self, key)._format = self.format[key]

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

