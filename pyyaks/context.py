import re
import os
import time
import stat
import pdb
import logging
import cPickle as pickle

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
            ids = [x-1 for x in argids] if argids else range(len(args))
            newargs = [(render(x) if i in ids else x) for (i, x) in enumerate(args)]
            return func(*newargs, **kwargs)

        # Make an effort to copy func_name and func_doc.  Built-ins don't have these.
        try:   
            newfunc.func_name = func.func_name
            newfunc.func_doc = func.func_doc
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
    context = pickle.load(open(filename, 'r'))
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
    logger.verbose('Storing context to %s' % filename)
    if keys:
        dump_context = dict((x, CONTEXT[x]) for x in keys)
    else:
        dump_context = CONTEXT
    pickle.dump(dump_context, open(filename, 'w'))

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
        self._name = name
        self._basedir = basedir
        for attr in ('val', 'rel', 'abs', 'format'):
            setattr(self, attr, _ContextDictAccessor(self, attr))

    def __getitem__(self, key):
        """Get key value from the ContextDict.  For a ContextDict with base
        then allow for extensions on key.
        """
        match = re.match(r'([^.]+)\.(.+)', key)
        base, ext = match.groups() if match else (key, None)

        # Autogenerate an entry for key
        if base not in self:
            value = ContextValue(val=None, name=base, basedir=self._basedir)
            logger.debug('Autogen %s with name=%s basedir=%s' % (repr(value), base, self._basedir))
            dict.__setitem__(self, base, value)

        baseContextValue = dict.__getitem__(self, base)
        return (ContextValue(baseContextValue, ext=ext) if ext else baseContextValue)

    def __setitem__(self, key, val):
        # If ContextValue was already init'd then just update val
        if key in self:
            value = dict.__getitem__(self, key)
            logger.debug('Setting value %s with name=%s val=%s basedir=%s' % (repr(value), repr(key), repr(val), self._basedir))
            value.val = val
        else:
            if '.' in key:
                raise ValueError('Dot not allowed in ContextDict key ' + key)
            value = ContextValue(val=val, name=key, basedir=self._basedir)
            logger.debug('Creating value %s with name=%s val=%s basedir=%s' % (repr(value), repr(key), repr(val), self._basedir))
            dict.__setitem__(self, key, value)

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

