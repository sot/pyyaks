from __future__ import print_function, division, absolute_import

import re
import os
import time
import stat
import pdb
import logging

from six.moves import cPickle as pickle
from copy import deepcopy

import jinja2
import pyyaks.fileutil

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

logger = logging.getLogger('pyyaks')
logger.addHandler(NullHandler())
logger.propagate = False

CONTEXT = {}

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
            ids = [x-1 for x in argids] if argids else list(range(len(args)))
            newargs = [(render(x) if i in ids else x) for (i, x) in enumerate(args)]
            return func(*newargs, **kwargs)

        # Make an effort to copy func_name and func_doc.  Built-ins don't have these.
        try:   
            newfunc.__name__ = func.__name__
            newfunc.__doc__ = func.__doc__
        except AttributeError:
            pass

        return newfunc
    return decorate

def update_context(filename, keys=None):
    """Update the current context from ``filename``.  This file should be
    created with ``store_context()``.

    :param filename: name of file containing context
    :param keys: list of keys in CONTEXT to update (default=None => all)
    :rtype: None
    """
    logger.verbose('Restoring context from %s' % filename)
    context = pickle.load(open(filename, 'rb'))
    for name in context:
        if keys and name not in keys:
            continue
        if name not in CONTEXT:
            raise KeyError('ContextDict %s found in %s but not in existing CONTEXT' %
                           (name, filename))
        CONTEXT[name].update(context[name])
        
def store_context(filename, keys=None):
    """Store the current context to ``filename``.

    :param filename: name of file for storing context
    :param keys: list of keys in CONTEXT to store (default=None => all)
    :rtype: None
    """
    if filename:
        logger.verbose('Storing context to %s' % filename)
        if keys:
            dump_context = dict((x, CONTEXT[x]) for x in keys)
        else:
            dump_context = CONTEXT
        pickle.dump(dump_context, open(filename, 'wb'))

class ContextValue(object):
    """Value with context that has a name and modification time. 

    :param val: initial value (optional)
    :param name: context value name
    :param basedir: root directory for a file context value
    :param format: optional format specifier when rendering value
    :param ext: extension to be added when rendering a file context value
    """
    def __init__(self, val=None, name=None, format=None, ext=None, parent=None):
        # Possibly inherit attrs (except for 'ext') from an existing ContextValue object
        if isinstance(val, ContextValue):
            for attr in ('_val', '_mtime', '_name', 'parent', 'format'):
                setattr(self, attr, getattr(val, attr))
        else:
            self._val = val
            self._mtime = None if val is None else time.time()
            self._name = name
            self.parent = parent
            self.format = format

        self.ext = ext

    def clear(self):
        """Clear the value, modification time, and format (set to None)"""
        self._val = None
        self._mtime = None

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
    def fullname(self):
        return (self.parent._name + '.' + self.name) if self.parent else self.name

    @property
    def name(self):
        return self._name + ('.' + self.ext if self.ext else '')

    @property
    def basedir(self):
        return None if (self.parent is None) else self.parent.basedir

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
            raise ValueError("Context value '%s' is undefined" % self.fullname)
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
            ext = ('.' + self.ext if self.ext else '')
            strval0 = strval
            for basedir in self.basedir.split(':'):
                strval = pyyaks.fileutil.relpath(os.path.join(basedir, strval0) + ext)
                if os.path.exists(strval):
                    break

        return strval

    @property
    def type(self):
        return 'value' if (self.basedir is None) else 'file'

    @property
    def rel(self):
        """File context value as a relative path or self._val if not a file.

        Basedir can have multiple base paths separated by ':' like the linux
        PATH.  The first base path for which the content file path exists is
        returned, or if none exist then the last relative path will be returned.
        """
        return str(self)

    @property
    def abs(self):
        """File context value as an absolute path or self._val if not a file

        Basedir can have multiple base paths separated by ':' like the linux
        PATH.  The first base path for which the content file path exists is
        returned, or if none exist then the last absolute path will be returned.
        """
        return str(self._val) if (self.basedir is None) else  os.path.abspath(str(self))

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
    when assigning to a dict key.  If no ``name`` is supplied then the
    ContextDict is not registered in the global CONTEXT.

    :param name: name by which dictionary is registered in context.
    :param basedir: base directory for file context
    """
    def __new__(cls, name=None, basedir=None):
        if name in CONTEXT:
            if basedir != CONTEXT[name].basedir:
                raise ValueError("Re-using context name '{}' but basedirs don't match "
                                 "({} vs. {})".format(name, basedir, CONTEXT[name].basedir))
            return CONTEXT[name]

        self = super(ContextDict, cls).__new__(cls)
        if name is not None:
            CONTEXT[name] = self
        self._name = name
        self.basedir = basedir
        self._context_manager_cache = []
        for attr in ('val', 'rel', 'abs', 'format'):
            setattr(self, attr, _ContextDictAccessor(self, attr))
        return self

    def __init__(self, *args, **kwargs):
        # Initialization is done in __new__, so don't do anything here
        pass

    def __getitem__(self, key):
        """Get key value from the ContextDict.  For a ContextDict with base
        then allow for extensions on key.
        """
        match = re.match(r'([^.]+)\.(.+)', key)
        base, ext = match.groups() if match else (key, None)

        # Autogenerate an entry for key
        if base not in self:
            value = ContextValue(val=None, name=base, parent=self)
            logger.debug('Autogen %s with name=%s basedir=%s' %
                         (repr(value), base, self.basedir))
            dict.__setitem__(self, base, value)

        baseContextValue = dict.__getitem__(self, base)
        return (ContextValue(baseContextValue, ext=ext) if ext else baseContextValue)

    def __setitem__(self, key, val):
        # If ContextValue was already init'd then just update val
        if key in self:
            value = dict.__getitem__(self, key)
            logger.debug('Setting value %s with name=%s val=%s basedir=%s' %
                         (repr(value), repr(key), repr(val), self.basedir))
            value.val = val
        else:
            if '.' in key:
                raise ValueError('Dot not allowed in ContextDict key ' + key)
            value = ContextValue(val=val, name=key, parent=self)
            logger.debug('Creating value %s with name=%s val=%s basedir=%s' %
                         (repr(value), repr(key), repr(val), self.basedir))
            dict.__setitem__(self, key, value)

    def __enter__(self):
        """
        Context manager to cache this ContextDict object::

          context_val = Context('context_val')
          with context_val:
              pass
        """
        # Push a copy of self onto a stack
        self._context_manager_cache.append(deepcopy(self))

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Pop the most recent cached version and update self
        self_cache = self._context_manager_cache.pop()
        self.update(self_cache)

        # Delete any keys now in self that weren't in the cached version
        delkeys = [key for key in self if key not in self_cache]
        for key in delkeys:
            del self[key]

    def cache(self, func):
        """
        Decorator to cache this ContextDict object
        """
        import functools

        @functools.wraps(func)
        def wrap_func(*args, **kwargs):
            self_cache = deepcopy(self)

            try:
                result = func(*args, **kwargs)
            finally:
                # Restore to self_cache and delete any keys now in self that weren't in the
                # cached version
                self.update(self_cache)
                delkeys = [key for key in self if key not in self_cache]
                for key in delkeys:
                    del self[key]

            return result

        return wrap_func

    def update(self, vals):
        if hasattr(vals, 'items'):
            vals = vals.items()
        for key, val in vals:
            self[key] = val

    def __repr__(self):
        return str(dict((key, self[key].val) for key in self))

    def clear(self):
        """Clear all values in dictionary.  The keys are not deleted so that
        ContextValue references in task decorators maintain validity."""
        for key in self:
            dict.__getitem__(self, key).clear()

    def get_basedir(self):
        return self._basedir

    def set_basedir(self, val):
        if val is None:
            self._basedir = None
        else:
            # Split on : which is not followed by \ (which would almost certainly
            # be a Windows file path like C:\\Users).
            non_windows_colon = re.compile(r':(?=[^\\])')
            vals = [os.path.abspath(x) for x in non_windows_colon.split(val)]
            self._basedir = ':'.join(vals)

    basedir = property(get_basedir, set_basedir)


class _ContextDictAccessor(object):
    """Get or set ContextValue attributes via object attribute syntax through ContextDict.

    Examples::

      src = ContextDict('src')
      src.val.joe = 2    # same as src['joe'] = 2
      x = src.val.joe    # src['joe'].val
      src.format.joe = '%03d'
      print src['joe']

      files = ContextDict('files', basedir='.')
      files['jane'] = '{{src.joe}}/jane'
      print files.rel.jane
      print files.abs.jane
    """
    def __init__(self, contextdict, attr):
        object.__setattr__(self, '_contextdict', contextdict)
        object.__setattr__(self, '_attr', attr)

    def __getattr__(self, name):
        # pickle looks for some specific attributes beginning with __ and expects
        # AttributeError if they are not provided by class.
        if name.startswith('__'):
            raise AttributeError

        return getattr(self._contextdict[name], self._attr)

    def __setattr__(self, name, value):
        setattr(self._contextdict[name], self._attr, value)
        
    def __getitem__(self, name):
        return self.__getattr__(name)
    
    def __setitem__(self, name, value):
        self.__setattr__(name, value)

