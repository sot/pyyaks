"""Customize logging to add a VERBOSE level and provide a logger for which
the trailing newline can be suppressed.
"""
import logging
import types
from logging import NOTSET, DEBUG, INFO, WARNING, CRITICAL, ERROR
import sys
import contextlib

@contextlib.contextmanager
def newlines_suppressed(logger):
    """Context manager to suppress newline output for each handler in the
    supplied ``logger``.  Example::

      with newlines_suppressed(logger):
          logger.info('Starting something ... ')
      # process ...
      logger.info('done')

    :param logger: logger object created with ``get_logger()``
    """
    current = []
    try:
        for handler in logger.handlers:
            current.append(getattr(handler, 'suppress_newline', False))
            handler.suppress_newline = True
        yield
    finally:
        for handler, suppress_newline in zip(logger.handlers, current):
            handler.suppress_newline = suppress_newline

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

# Add a verbose level
VERBOSE = 15
logging.VERBOSE = VERBOSE
logging.addLevelName(VERBOSE, 'VERBOSE')

def emit_newline_optional(handler, record):
    """Same as logging.Handler.emit but with an option to suppress the
    trailing newline if a Handler attribute suppress_newline is True. If the
    attribute is not True or does not exist then there is no change from the
    normal behavior.
    """
    try:
        msg = handler.format(record)
        fs = "%s" if getattr(handler, 'suppress_newline', None) else "%s\n"
        if not hasattr(types, "UnicodeType"): #if no unicode support...
            handler.stream.write(fs % msg)
        else:
            try:
                handler.stream.write(fs % msg)
            except UnicodeError:
                handler.stream.write(fs % msg.encode("UTF-8"))
        handler.flush()
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        handler.handleError(record)

logging.StreamHandler.emit = emit_newline_optional

def get_logger(filename=None, filemode='w', format='%(message)s',
                 datefmt=None, level=logging.INFO, stream=sys.stdout, filelevel=None,
                 name='pyyaks'):
    """
    Do basic configuration for the logging system. Similar to
    logging.basicConfig but the logger name is configurable and both a file
    output and a stream output can be created. 
    
    Returns a logger object.  For this logger the trailing newline in invidual
    handlers can be suppressed by setting the ``suppress_newline`` attribute
    to True for that handler.  More normally use the ``newlines_suppressed``
    context manager.
    
    The default behaviour is to create a StreamHandler which writes to
    sys.stdout, set a formatter using the "%(message)s" format string, and
    add the handler to the "pyyaks" logger.

    A number of optional keyword arguments may be specified, which can alter
    the default behaviour.

    :param filename: create FileHandler using the specified filename
    :param filemode: open ``filename`` with specified filemode
    :param format: handler format string
    :param datefmt: handler date/time format specifier
    :param level:  logger level (default=INFO).
    :param filelevel: logger level for the file logger.  defaults to
            ``level`` if not specified.
    :param stream: initialize the StreamHandler using ``stream``
              Defaults to sys.stdout.  Set to None to disable.
    :param name: Logger name
    """
    # Get a logger for the specified name and remove existing handlers
    logger = logging.getLogger(name)
    logger.setLevel(DEBUG)
    for hdlr in [h for h in logger.handlers]:
        logger.removeHandler(hdlr)
        
    fmt = logging.Formatter(format, datefmt)

    # Add handlers. Add NullHandler if no file or stream output so that
    # modules don't emit a warning about no handler.
    if not (filename or stream):
        logger.addHandler(NullHandler())

    if filename:
        hdlr = logging.FileHandler(filename, filemode)
        hdlr.setLevel(level if filelevel is None else filelevel)
        hdlr.setFormatter(fmt)
        logger.addHandler(hdlr)

    if stream:
        hdlr = logging.StreamHandler(stream)
        hdlr.setLevel(level)
        hdlr.setFormatter(fmt)
        logger.addHandler(hdlr)

    # Add a VERBOSE level and define method to use it
    logger.verbose = lambda msg: logger.log(logging.VERBOSE, msg)
    
    return logger
