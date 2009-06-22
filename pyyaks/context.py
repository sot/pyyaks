import re
import os
import time
import stat
import pdb

import django.template
import django.conf
import Ska.File
import pyyaks.logger as logger

Context = {}

try:
    django.conf.settings.configure()
except RuntimeError, msg:
    print msg
    pass

def render(s):
    """Convenience function to create an anonymous Value and then render it."""
    if isinstance(s, Value):
        return str(s)
    else:
        return str(Value(s))

def render_args(*argids):
    """Decorate a function so that the specified arguments are rendered via
    context.render() before being passed to function.  Keyword arguments are
    unaffected.

    Examples::
    
      # Apply render() to all 3 args
      @context.render_args()
      def func(arg1, arg2, arg3):
          return arg1, arg2, arg3

      # Render just arg1
      @context.render_args(1)
      def func(arg1, arg2, arg3):
          return arg1, arg2, arg3

      # Render arg1 and arg3
      @context.render_args(1, 3)
      def func(arg1, arg2, arg3):
          return arg1, arg2, arg3
    """
    def decorate(func):
        def newfunc(*args, **kwargs):
            ids = [x-1 for x in argids] if argids else range(len(args))
            newargs = [(render(x) if i in ids else x) for (i, x) in enumerate(args)]
            return func(*newargs, **kwargs)

        newfunc.func_name = func.func_name
        newfunc.func_doc = func.func_doc
        return newfunc
    return decorate

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

    def clear(self):
        self._val = None
        self._mtime = None

    def getval(self):
        return self._val

    def setval(self, val):
        if isinstance(val, Value):
            self.__init__(val, ext=val.ext)
        else:
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
        strval = val = self._val
        Django_tag = re.compile(r'{[%{]')
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
            # Note that os.path.join(a,b) returns b is b is already absolute
            strval = Ska.File.relpath(os.path.join(self.basedir, strval)
                                      + ('.' + self.ext if self.ext else ''))
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
        # pickle looks for some specific attributes beginning with __ and expects
        # AttributeError if they are not provided by class.
        if ext.startswith('__'):
            raise AttributeError
        else:
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
            value = Value(val=None, name=base, basedir=self.basedir)
            logger.debug('Autogen %s with name=%s basedir=%s' % (repr(value), base, self.basedir))
            dict.__setitem__(self, base, value)

        baseValue = dict.__getitem__(self, base)
        return (Value(baseValue, ext=ext) if ext else baseValue)

    def __setitem__(self, key, val):
        # If ContextValue was already init'd then just update val
        if key in self:
            value = dict.__getitem__(self, key)
            print 'Setting value', repr(value), ' with name=', key, 'val=', val, 'basedir=', self.basedir
            value.val = val
        else:
            if '.' in key:
                raise ValueError('Dot not allowed in ContextDict key ' + key)
            value = Value(val=val, name=key, basedir=self.basedir)
            # print 'Creating value with name= val= basedir=%s', repr(value), key, val, self.basedir
            logger.debug('Creating value %s with name=%s val=%s basedir=%s' % (repr(value), key, str(val), self.basedir))
            dict.__setitem__(self, key, value)

    def update(self, vals):
        if hasattr(vals, 'items'):
            vals = vals.items()
        for key, val in vals:
            self[key] = val

    def accessor(self):
        return ContextDictAccessor(self)

    def __repr__(self):
        return str(dict((key, self[key].val) for key in self))

    def clear(self):
        for key in self:
            dict.__getitem__(self, key).clear()

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
        if self._contextdict.basedir is None:
            return self._contextdict[name].val
        else:
            return self._contextdict[name].rel

    def __setattr__(self, name, value):
        self._contextdict[name] = value
        
    def __getitem__(self, name):
        return self.__getattr__(name)
    
    def __setitem__(self, name, value):
        self.__setattr__(name, value)

