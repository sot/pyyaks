Pyyaks
==================================

``Pyyaks`` is a toolkit for building data processing pipelines.  The current
release is an alpha version which has been tested and used internally for
production processing but not tested or reviewed by others.

Features
--------

The ``pyyaks`` package provides a number of features that facilitate creating
and running data processing pipelines.  The fundamental concept of a pipeline
in this context is a set of connected processing tasks that are run in order to
create predefined output files from a set of input data and/or files.  

Pipeline definition
  Pipeline is just the code that runs between special start and stop routines.
  There is no requirement to have a pre-defined linear flow.

Task definition
  Pipeline tasks are defined as python functions wrapped ``pyyaks`` task decorators.

Logging
  ``Pyyaks`` provides a module to easily configure output logging to the screen
  and a file, providing consistent output control.  An additional "verbose"
  logging level is provided as well as a way to suppress the usual trailing
  newline of logging output.

Error handling
  Exceptions are always handled and reported and set a pipeline failure flag.
  Subsequent pipeline tasks can be configured to run even in the event of a
  previous failure.

Context values 
  The idea of context from template rendering engines (jinja2, django) is used
  in ``pyyaks``.  Pipeline variables are maintained as ContextValue objects in
  a global context dictionary.  ContextValue objects have a modification time,
  preferred output formatting, and when accessed in string context are rendered
  by the jinja2 template engine.

File aliasing
  ContextValue objects can also represent a file path with convenient access to
  absolute path and relative path from the current directory.  This allows upfront
  definition of the pipeline file hierarchy.

Dependencies
  The usual concept of dependent and target files is extended to apply also to
  pipeline context values.  Thus a task can depend on certain context values 
  and be required to have updated other values.

Subprocess management
  ``Pyyaks`` includes a module that puts single- or multi-line bash shell
  scripts under pipeline control.  It also provides a simple interface to the
  ``subprocess`` module for spawning jobs with a timeout and exception
  handling.

Templating
  The global context dictionary of pipeline values and files makes it simple to
  create processing output files (e.g. HTML reports) using a template rendering
  engine such as ``jinja2``.

Concurrency
  ``Pyyaks`` applications can easily use ``multiprocessing`` to fully utilize
  multicore machines.  An example is given in the code examples directory.

