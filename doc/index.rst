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

Requirements
------------

``Pyyaks`` requires python version 2.5 or greater (but not python 3).  The only
3rd party module required is Jinja2.

Download
----------

The ``pyyaks`` package is available for
download at `<http://cxc.harvard.edu/contrib/pyyaks/downloads>`_.  

Tutorial
-----------------

The example code ``examples/skyview.py`` shows the basic working structure of a
pipeline implemented with ``pyyaks``.  The project here is to start from a
record list of interesting astronomical sources (with name, id, position, image
catalog) and generate HTML pages with the basic source information and an image
retrieved from the HEASARC Skyview web server.

Setup
^^^^^^^^^^^
**Import modules**

The ``pyyaks`` package provides five key modules.  The only required module
is ``pyyaks.task`` which provides the base tools for constructing a pipeline.
::

  import pyyaks.task       # Pipeline definition and execution
  import pyyaks.logger     # Output logging control
  import pyyaks.context    # Template rendering to provide context values
  import pyyaks.shell      # Sub-process control e.g. spawning shell commands
  import pyyaks.fileutil   # File utilities

**Initialize source data**

Initialize the list of records describing the sources to be processed.
More typically this type of data would come from an input file.
::

  source_cols = ('id', 'ra_hms',     'dec_dms',      'name',          'size', 'survey')
  sources =    ((100, "10 45 03.59", "-59 41 04.24", "Eta Carinae",   1.0,   "DSS"),
                (101, "12 18 56.40", "+14 23 59.21 ", "Nice Galaxy",  3.0,   "DSS"),
                )

**Initialize context dictionary to hold source information**

This key step initializes a persistent global "context dictionary" that is used
to capture the properties of the source currently being processed.  A context
dictionary is a modified python dictionary containing context value objects.
Further explanation and examples of this key concept are found in the
``pyyax.context``_ module documentation.  In this example we also define an
output format specification for ``ra`` and ``dec``.  This determines how these
values will be formatted whenever output in a string context, e.g. when
rendered in an output template.

::

  source = pyyaks.context.ContextDict('source')
  source['ra'].format = '%.5f'
  source['dec'].format = '%.4f'

**Initialize context dictionary to define processing file hierarchy**

Now we define the file hierarchy for each processed source as a context
dictionary.  By including a ``basedir`` keyword argument the associated context
objects are treated as file paths.  This means that when output in a string
context the value is treated as a file path relative to ``basedir`` (unless it
is already an absolute path).  The normal output in string context is a path
which is relative to the current working directory.

::

  files = pyyaks.context.ContextDict('files', basedir='data')
  files.update({'source_dir': '{{source.id}}',
                'image':      '{{source.id}}/image',
                'context':    '{{source.id}}/context',
                'index':      '{{source.id}}/index',
               })

**Initialize default pyyaks logging to a file 'run.log' and stdout**

``Pyyaks`` includes a wrapper around the python ``logging`` module
to standardize output logging within all modules and user code.

::

  loglevel = pyyaks.logger.INFO
  logfile = 'run.log'
  logger = pyyaks.logger.get_logger(level=loglevel, filename=logfile)


Pipeline processing tasks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The tasks that comprise the pipeline are defined as decorated python functions.
The ``pyyaks.task`` decorators are the "magic" that provide the exception handling,
dependency checking and other features required of pipeline processing. 

Every task definition must start with the ``@pyyaks.task.task()`` decorator
which provides exception handling and basic task reporting.  Other available
``pyyaks.task`` decorators are ``depends()``, ``chdir()``, and ``setenv()``.

A processing failure can result from any raised exception or failure to meet
the dependence criteria (either on task entrance or exit).  Subsequent pipeline
tasks are not run, with the exception of tasks defined with the decorator
``@pyyaks.task.task(run=True)``.  Typically this would include tasks that
generate reports and can therefore provide diagnostics of task failures.

**Task with file target dependency**

This shows a task that must create a particular file specified in the list of
``targets``.  If that file already exists then the task will not be run, and if
the file does not exist after the task runs then a processing failure occurs.

::

  @pyyaks.task.task()
  @pyyaks.task.depends(targets=(files['source_dir'],))
  def make_source_dir():
      """Make the directory that holds outputs for the source."""

      os.makedirs(files['source_dir'].rel)

**Task with value dependencies**

Traditional pipeline task dependencies are limited to dependent and target
files, but ``pyyaks`` extends that concept to context values (which also have a
persistent modification time).  

::

  @pyyaks.task.task()
  @pyyaks.task.depends(depends=(source['ra_hms'], source['dec_dms']),
                       targets=(source['ra'], source['dec']))
  def calc_ra_dec():
      """Calculate decimal RA and Dec from sexigesimal input in source data."""
      
      pos_str = source['ra_hms'].val + " " + source['dec_dms'].val
      pos_str = re.sub(r'[,:dhms]', ' ', pos_str)
      args = pos_str.split()

      # ... CALCULATIONS here ...

      source['ra'] = ra
      source['dec'] = dec
      logger.verbose(pyyaks.context.render('RA={{source.ra}} Dec={{source.dec}}'))


**Task run within a directory**

This task creates an HTML report page by rendering a template HTML document
within the current context (i.e. the source and files context dictionaries).  A
key feature here is that the HTML page needs to refer to the ``image.gif`` file
by a file link relative to the location of the HTML file.  To accomplish this
we use the ``chdir(dir)`` directory to run the task within the specified
directory.  This assures the correct starting path when the
``{{files.image.gif}}`` value is rendered within the HTML template.

::

  @pyyaks.task.task()
  @pyyaks.task.chdir(files['source_dir'])
  def make_html(depends=(files['image.gif'],),
                targets=(files['index.html'],)):
      """Create a simple HTML report page for this source."""

      index_html = open(files['index.html'].rel, 'w')
      index_html.write(pyyaks.context.render(html_template))
      index_html.close()

Run the pipeline for each source 
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After setting up all the pipeline infrastructure it is straightforward to run
the actual pipeline.  There are a few key elements that are normally part of
the ``pyyaks`` idiom: 

- Set values in a context dictionary to reflect the processing iteration.
- Call ``pyyaks.task.start()`` to start the pipeline sequence.
- Call task functions to do pipeline processing.
- Call ``pyyaks.task.end()`` to end the pipeline sequence.

For the ``skyview.py`` example this becomes::

  for src in sources:
      # 'source' is a persistent global so the data values should be cleared for each loop
      source.clear()

      # Set global source attributes ('name', 'id', 'ra_hms', etc) from inputs 'sources' values
      source.update(zip(source_cols, src))

      process_msg = 'Processing source id=%s name=%s' % (source['id'], source['name'])

      # Start the pyyaks pipeline.  This includes restoring previous processing results from
      # a 'context' file.
      pyyaks.task.start(message=process_msg, context_file=files['context.pkl'].rel)

      # Call the actual pipeline functions
      make_source_dir()
      calc_ra_dec()
      get_image()
      make_html()

      # Declare the end of the pipeline and store processing results to file.
      pyyaks.task.end(message=process_msg, context_file=files['context.pkl'].rel)

API documentation
-----------------
.. toctree::
   :maxdepth: 1

   context
   fileutil
   logger
   shell
   task

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

