import re
import os
import time
import stat
import pdb
import logging
import cPickle as pickle

import jinja2
import pyyaks.fileutil

CONTEXT = {}
logger = logging.getLogger('pyyaks')

def render(val):
    """Render ``val`` using the template engine and the current context.

    :param val: input value

    :returns: rendered value
    """
    if isinstance(val, ContextValue):
        return str(val)
    else:
        return str(ContextValue(val))

def render_args(*argids):
    """
    Decorate a function so that the specified arguments are rendered via
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

def update_context(filename):
    """Update the current context from ``filename`` if it exists.  This file
    should be created with ``store_context()``.

    :param filename: name of file containing context
    :rtype: None
    """
    if os.path.exists(filename):
        logger.verbose('Restoring context from %s' % filename)
        context = pickle.load(open(filename, 'r'))
        for name in context:
            if name not in CONTEXT:
                tmp = ContextDict(name, basedir=context[name].basedir)
            CONTEXT[name].update(context[name])
        
def store_context(filename):
    logger.verbose('Storing context to %s' % filename)
    pickle.dump(CONTEXT, open(filename, 'w'))

class ContextValue(object):
    """Value with context that has a name and modification time. 

    :param val: initial value (optional)
    :param name: context value name
    :param basedir: root directory for a file context value
    :param format: optional format specifier when rendering value
    :param ext: extension to be added when rendering a file context value
    """
    def __init__(self, val=None, name=None, basedir=None, format=None, ext=None):
        # Possibly inherit attrs (except for 'ext') from an existing ContextValue object
        if isinstance(val, ContextValue):
            for attr in ('_val', '_mtime', 'name', 'basedir', 'format'):
                setattr(self, attr, getattr(val, attr))
        else:
            self._val = val
            self._mtime = None if val is None else time.time()
            self.name = name
            self.basedir = basedir and os.path.abspath(basedir)
            self.format = format

        self.ext = ext

    def clear(self):
        """Clear the value, modification time, and format (set to None)"""
        self._val = None
        self._mtime = None
        self.format = None

    def getval(self):
        return self._val

    def setval(self, val):
        if isinstance(val, ContextValue):
            self.__init__(val, ext=val.ext)
        else:
            self._val = val
            self._mtime = time.time()

    val = property(getval, setval)
    """Set or get with the ``val`` attribute"""

    @property
    def mtime(self):
        """Modification time"""
        if self.basedir:
            filename = str(self)
            return (os.stat(filename)[stat.ST_MTIME] if os.path.exists(filename) else None)
        else:
            return self._mtime

    def __unicode__(self):
        return str(self)
    
    def __str__(self):
        strval = val = self._val
        if val is None:
            raise ValueError("Context value '%s' is undefined" % self.name)
        template_tag = re.compile(r'{[%{]')
        try:                            
            # Following line will give TypeError unless val is string-like
            while (template_tag.search(val)):
                template = jinja2.Template(val)
                strval = template.render(CONTEXT)
                if strval == val:
                    break
                else:
                    val = strval
        except TypeError:
            strval = (self.format or '%s') % val

        if self.basedir:
            # Note that os.path.join(a,b) returns b is b is already absolute
            strval = pyyaks.fileutil.relpath(os.path.join(self.basedir, strval)
                                      + ('.' + self.ext if self.ext else ''))
        return strval

    @property
    def rel(self):
        """File context value as a relative path"""
        return str(self)

    @property
    def abs(self):
        """File context value as an absolute path"""
        return os.path.abspath(str(self))

    def __getattr__(self, ext):
        """Interpret an unfound attribute lookup as a file extension.
        A new ContextValue object with that extension is returned.
        """
        # pickle looks for some specific attributes beginning with __ and expects
        # AttributeError if they are not provided by class.
        if ext.startswith('__'):
            raise AttributeError
        else:
            return ContextValue(val=self, ext=ext)

class ContextDict(dict):
    """Dictionary class that automatically registers the dict in the module
    CONTEXT and overrides __setitem__ to create an appropriate ContextValue
    when assigning to a dict key.

    :param name: name by which dictionary is registered in context.
    :param basedir: base directory for file context
    """
    def __init__(self, name, basedir=None):
        dict.__init__(self)
        CONTEXT[name] = self
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
            value = ContextValue(val=None, name=base, basedir=self.basedir)
            logger.debug('Autogen %s with name=%s basedir=%s' % (repr(value), base, self.basedir))
            dict.__setitem__(self, base, value)

        baseContextValue = dict.__getitem__(self, base)
        return (ContextValue(baseContextValue, ext=ext) if ext else baseContextValue)

    def __setitem__(self, key, val):
        # If ContextValue was already init'd then just update val
        if key in self:
            value = dict.__getitem__(self, key)
            logger.debug('Setting value %s with name=%s val=%s basedir=%s' % (repr(value), key, val, self.basedir))
            value.val = val
        else:
            if '.' in key:
                raise ValueError('Dot not allowed in ContextDict key ' + key)
            value = ContextValue(val=val, name=key, basedir=self.basedir)
            logger.debug('Creating value %s with name=%s val=%s basedir=%s' % (repr(value), key, val, self.basedir))
            dict.__setitem__(self, key, value)

    def update(self, vals):
        if hasattr(vals, 'items'):
            vals = vals.items()
        for key, val in vals:
            self[key] = val

    def accessor(self):
        """Return a ContextDictAccessor for the dictionary"""
        return ContextDictAccessor(self)

    def __repr__(self):
        return str(dict((key, self[key].val) for key in self))

    def clear(self):
        """Clear all values in dictionary.  The keys are not deleted so that
        ContextValue references in task decorators maintain validity."""
        for key in self:
            dict.__getitem__(self, key).clear()

class ContextDictAccessor(object):
    """Convenience class to get or set ContextDict values via object
    attribute syntax. If the ContextValue represents a file path (basedir
    attribute is defined) then the rendered relative path name is returned.

    Example::

      from pyyaks.context import (ContextDict, ContextDictAccessor)
      SRC = ContextDict('src')
      Src = SRC.accessor()
      SRC['test'] = 5.2
      print Src.test
      Src.test = 8
      print SRC['test'].val
      
      FILE = ContextDict('file', basedir='.')
      File = ContextDictAccessor(FILE)
      File.obs_dir = 'obs{{src.test}}/'
      print File.obs_dir
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

