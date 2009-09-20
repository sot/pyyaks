#!/usr/bin/env python
import os
import re
import urllib
import pdb

import pyyaks.task
import pyyaks.logger
import pyyaks.context
from pyyaks.task import task, chdir, setenv, depends

#######################################################################
# Initialize data and pyyaks components
#######################################################################

source_cols = ('id', 'ra_hms',     'dec_dms',      'name',          'size', 'survey')
sources =    ((100, "10 45 03.59", "-59 41 04.24", "Eta Carinae",   1.0,   "DSS"),
              (101, "12 18 56.40", "+14 23 59.21 ", "Nice Galaxy",  3.0,   "DSS"),
              )

# Template for a simple HTML report page for each source
html_template = """
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<body>
<h2> Skyview image for {{source['name']}} (id={{source.id}})</h2>
<table>
    <tr>
      <td>
        <table>
    	   <tr> <td>Name  </td> <td> {{ source.name }} </td> </tr>
    	   <tr> <td>Id    </td> <td> {{ source.id }} </td> </tr>
    	   <tr> <td>RA    </td> <td> {{ source.ra_hms }} = {{source.ra}} </td> </tr>
    	   <tr> <td>Dec   </td> <td> {{ source.dec_dms }} = {{source.dec}} </td> </tr>
    	   <tr> <td>Size  </td> <td> {{ source.size }} degrees </td> </tr>
    	   <tr> <td>Survey</td> <td> {{ source.survey }} </td> </tr>
        </table>
      </td>
      <td style="padding:10"> <img src="{{files.image.gif}}">
      </td>
    </tr>
</table>

 <hr>
 <address>Created by pyyaks</address>
</body>
</html>
"""

# Initialize context dictionary to hold source information
source = pyyaks.context.ContextDict('source')
source['ra'].format = '%.5f'
source['dec'].format = '%.4f'

# Initialize context dictionary to define processing file hierarchy 
# from a base directory 'data'
files = pyyaks.context.ContextDict('files', basedir='data')
files.update({'source_dir': '{{source.id}}',
              'image':      '{{source.id}}/image',
              'context':    '{{source.id}}/context',
              'index':      '{{source.id}}/index',
             })

# Initialize default pyyaks logging to a file 'run.log' and stdout
loglevel = pyyaks.logger.INFO
logfile = 'run.log'
logger = pyyaks.logger.get_logger(level=loglevel, filename=logfile)

#######################################################################
# Define the processing tasks (functions) that comprise the pipeline.
#######################################################################

@task()
@depends(targets=(files['source_dir'],))
def make_source_dir():
    """Make the directory that holds outputs for the source."""

    os.makedirs(files['source_dir'].rel)


@task()
@depends(depends=(source['ra_hms'], source['dec_dms']),
         targets=(source['ra'], source['dec']))
def calc_ra_dec():
    """Calculate decimal RA and Dec from sexigesimal input in source data."""
    
    pos_str = source['ra_hms'].val + " " + source['dec_dms'].val
    pos_str = re.sub(r'[,:dhms]', ' ', pos_str)
    args = pos_str.split()

    if len(args) != 6:
        raise ValueError("Input source position '%s' needs 6 values" % pos_str)

    rah = int(args[0])
    ram = int(args[1])
    ras = float(args[2])
    decsign = '-' if args[3].startswith('-') else '+'
    decd = abs(int(args[3]))
    decm = int(args[4])
    decs = float(args[5])

    ra = 15.0 * (rah + ram/60. + ras/3600.)
    dec = abs(decd) + decm/60. + decs/3600.
    if decsign == '-':
        dec = -dec

    source['ra'] = ra
    source['dec'] = dec
    logger.verbose(pyyaks.context.render('RA={{source.ra}} Dec={{source.dec}}'))


@task()
@depends(depends=(source['ra'], source['dec']),
         targets=(files['image.gif'],))
def get_image():
    """Get a sky image from skyview.gsfc.nasa.gov using the batch web interface
    described at http://skyview.gsfc.nasa.gov/docs/batchpage.html."""

    url = 'http://skyview.gsfc.nasa.gov/cgi-bin/images'
    data = dict(Position='%s,%s' % (source['ra'], source['dec']),
                Survey=source['survey'].val,
                Return='GIF',
                )
    urllib.urlretrieve(url, filename=files['image.gif'].rel, data=urllib.urlencode(data))


@task()
@depends()
@chdir(files['source_dir'])
def make_html(depends=(files['image.gif'],),
              targets=(files['index.html'],)):
    """Create a simple HTML report page for this source."""

    index_html = open(files['index.html'].rel, 'w')
    index_html.write(pyyaks.context.render(html_template))
    index_html.close()

#######################################################################
# Run the pipeline for each source 
#######################################################################
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

