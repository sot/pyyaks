#!/usr/bin/env python

import os
import re
import sys
import cPickle as pickle
import tempfile
import math
import shutil
import time
import pdb

import Ska.Shell
import Ska.File

import Ska.Table
import Ska.CIAO
import Chandra.ECF
import Ska.astro
import Ska.Numpy
import cosmocalc

import pyyaks.task
import pyyaks.logger as Log
import pyyaks.context
from pyyaks.task import task, chdir, setenv, depends
from pyyaks.context import render, ContextDict, render_args

def get_options():
    from optparse import OptionParser
    parser = OptionParser()
    parser.set_defaults()
    parser.add_option("--outdir",
                      default='testdata',
                      help="Directory for output data")
    parser.add_option("--logfile",
                      default='logs/%Y-%m-%d/%H:%M:%S',
                      help="File name for output logs in strftime format")
    parser.add_option("--loglevel",
                      default='debug',
                      help="Log level (debug|task|summary|quiet)")
    parser.add_option("--objlist",
                      default='sources/sdss_gal_stack0.dat.small',
                      help="Object list file")
    parser.add_option("--excllist",
                      default='sources/xsrclist4stackexcl.dat',
                      help="Excluded objects list file")
    parser.add_option("--aperture-size",
                      type='float',
                      default=0.9,
                      help="Source aperture size")
    parser.add_option("--aperture-unit",
                      default="ecf",
                      help="Source aperture units (ecf|kpc|pixel)")
    parser.add_option("--filter",
                      dest = 'filters',
                      default=['_row_ < 1'],
                      action='append',
                      help="Filter expression")
    (opt, args) = parser.parse_args()
    return (opt, args)

opt, args = get_options()

# Initialize output logging
loglevel = dict(debug=Log.DEBUG, task=Log.VERBOSE, summary=Log.INFO, quiet=60)[opt.loglevel]
logfile = time.strftime(opt.logfile)
logdir = os.path.dirname(logfile)
if not os.path.exists(logdir):
    os.makedirs(logdir)
Log.init(stdoutlevel=loglevel, filename=logfile, filelevel=loglevel, format="%(message)s")

# Create bash wrapper around Shell.bash.  This sets up a file-like object
# to stream shell pexpect output in a way that plays well with pyyaks.task output.
bash = pyyaks.task.bash(loglevel, oneline=True)

# Setup CIAO
ciaoenv = Ska.Shell.getenv('. /soft/ciao/bin/ciao.bash')
pfiles_dir = Ska.CIAO.localize_param_files(ciaoenv)

# Vars for staxx processing
# Configuration values
CFG = pyyaks.context.ContextDict('cfg')
CFG.update(dict(energy_filter = 'energy=500:7000',
                aperture_size = opt.aperture_size,
                aperture_unit = opt.aperture_unit,
                psf_energy = 1.5,       # kev
                excl_rad_ecf = 0.9,
                min_src_rad = 4,        # pixels
                bkg_ann_mul0 = 2.0,
                bkg_ann_mul1 = 7.0,
                sizefits = 80,
                sizejpg = 300,
                arcsec_per_pixel = 0.492, # ACIS plate scale
                ))
Cfg = CFG.accessor()

input_dir = 'champ*/OBS{{src.obsid.val|stringformat:"05d"}}/XPIPE' # Input data directory glob
log_file = 'staxx.log'                      # Yaxx log file or directory
evt2_glob   = 'evt2_ccdid{{src.ccdid}}.fits*'
expmap_glob = 'expmap_{{src.ccdid}}.fits*'
asol_glob   = 'pcad*_asol1.fits*'
prog_dir = os.path.abspath(os.path.dirname(__file__))

# Define file aliases
FILE = pyyaks.context.ContextDict('file', basedir=opt.outdir)
FILE.update(dict(
    resources_dir = 'resources/',
    index_template ='resources/index_template',
    pyaxx =         'resources/pyaxx',
    obs_dir =       'obs{{src.obsid}}/',
    obs_asol =      'obs{{src.obsid}}/asol',
    ccd_dir =       'obs{{src.obsid}}/ccd{{src.ccdid}}/',
    ccd_evt =       'obs{{src.obsid}}/ccd{{src.ccdid}}/acis_evt2',
    ccd_expmap =    'obs{{src.obsid}}/ccd{{src.ccdid}}/expmap',
    ccd_src_dir =   'obs{{src.obsid}}/ccd{{src.ccdid}}/{{src.xdat_id}}/',
    src_dir =       '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/',
    index =         '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/index',
    asol =          '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/asol',
    evt =           '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/acis_evt2',
    cut_evt =       '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/acis_cut_evt2',
    expmap =        '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/expmap',
    expmap_cut =    '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/expmap_cut',
    expmap_fill =   '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/expmap_fill',
    src =           '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/src',
    bkg =           '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/bkg',
    cut =           '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/cut',
    fill =          '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/fill',
    ds9 =           '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/ds9',
    apphot =        '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/apphot',
    apphot_exp =    '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/apphot_exp',
    src_img =       '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/acis_src_img',
    fill_img =      '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/acis_fill_img',
    info =          '{{src.xdat_id}}/obs{{src.obsid}}/ccd{{src.ccdid}}/info'))
File = FILE.accessor()

# Define src vars
SRC = pyyaks.context.ContextDict('src')
SRC['ra'].format = '%.5f'
SRC['dec'].format = '%.4f'
Src = SRC.accessor()

VAL = ContextDict('val')
Val = VAL.accessor()

# Set up a couple of functions for convenience
get_globfiles = render_args()(Ska.File.get_globfiles)
make_local_copy = render_args()(Ska.File.make_local_copy)

@pyyaks.context.render_args(1)
def make_dir(dir_):
    """Make a directory if it doesn't exist."""
    if not os.path.isdir(dir_):
        os.makedirs(dir_)
        if not os.path.isdir(dir_):
            raise pyyaks.task.TaskFailure('Failed to make directory %s' % dir_)
        Log.verbose('Made directory ' + dir_)
        
#####################################################################################
# Task definitions
#####################################################################################
@task()
@depends(targets=[FILE['src_dir'],
                  FILE['ccd_dir']])
def make_xdat_and_src_dirs():
    make_dir(File['src_dir'])
    make_dir(File['ccd_dir'])

###################################################################################
@task()
@chdir(FILE['ccd_dir'])
def make_xdat_to_src_link():
    if not os.path.exists(File['ccd_src_dir']):
        os.symlink(File['src_dir'], File['ccd_src_dir'])
        Log.verbose('Made symlink %s -> %s' % (File['src_dir'], File['ccd_src_dir']))

###################################################################################
@task()
def restore_src(filename):
    if os.path.exists(filename):
        Log.verbose('Restoring from %s' % filename)
        SRC.update(pickle.load(open(filename, 'r')))
        
###################################################################################
@task()
def store_src(filename):
    Log.verbose('Storing to %s' % filename)
    pickle.dump(SRC, open(filename, 'w'))

###################################################################################
@task()
@depends(depends=[os.path.join(prog_dir, 'pyaxx.css'),
                  os.path.join(prog_dir, 'index_template.html')],
         targets=[FILE['pyaxx.css'],
                  FILE['index_template.html']])
def copy_resources():
    make_dir(File['resources_dir'])
    for name in ('pyaxx.css', 'index_template.html'):
        Log.verbose('Copying %s to resources' % name)
        shutil.copy(os.path.join(prog_dir, name), File[name])

###################################################################################
@task()
@depends(targets=[FILE['ccd_evt.fits']])
def get_ccd_evt_fits():
    f = get_globfiles(os.path.join(input_dir, evt2_glob))[0]
    make_local_copy(f, File['ccd_evt.fits'], linkabs=True)
    Log.verbose('Made local copy %s -> %s' % (render(f), File['ccd_evt.fits']))


###################################################################################
@task()
@depends(targets=[FILE['ccd_expmap.fits']])
def get_ccd_expmap_fits():
    f = get_globfiles(os.path.join(input_dir, expmap_glob))[0]
    make_local_copy(f, File['ccd_expmap.fits'], linkabs=True)
    Log.verbose('Made local copy %s -> %s' % (render(f), File['ccd_expmap.fits']))

###################################################################################
@task()
@depends(depends=[FILE['ccd_evt.fits']],
         targets=[FILE['evt.fits']])
def get_evt_fits():
    make_local_copy(File['ccd_evt.fits'], File['evt.fits'])
    Log.verbose('Made local copy %s -> %s' % (File['ccd_evt.fits'], File['evt.fits']))

###################################################################################
@task()
@depends(depends=[FILE['ccd_expmap.fits']],
         targets=[FILE['expmap.fits']])
def get_expmap_fits():
    make_local_copy(File['ccd_expmap.fits'], File['expmap.fits'])
    Log.verbose('Made local copy %s -> %s' % (File['ccd_expmap.fits'], File['expmap.fits']))

###################################################################################
@task()
@depends(targets=(FILE['obs_asol.lis'],))
def get_obs_asol_files():
    files = get_globfiles(os.path.join(input_dir, asol_glob), maxfiles=None)
    obs_copies = [File['obs_asol'] + '_%d.fits' % i for i in range(len(files))]
    for f, l in zip(files, obs_copies):
        make_local_copy(f, l)
        Log.verbose('Made local copy %s -> %s' % (render(f), render(l)))

    obs_copies_base = [os.path.basename(x) for x in obs_copies]
    open(File['obs_asol.lis'], 'w').write('\n'.join(obs_copies_base))
    Log.verbose('Made %s' % File['obs_asol.lis'])

###################################################################################
@task()
@depends(depends=[FILE['ccd_evt.fits'],
                  FILE['obs_asol.lis'],
                  SRC['ra'],
                  SRC['dec']],
         targets=[SRC[x] for x in ('x', 'y', 'theta', 'phi')])
@setenv(ciaoenv)
def set_coords():
    kwargs = dict(evtfile=File['ccd_evt.fits'],
                  asolfile='@' + File['obs_asol.lis'],
                  pos=[Src.ra, Src.dec], coordsys='cel')
    Log.verbose('Running dmcoords(%s)' % str(kwargs))
    coords = Ska.CIAO.dmcoords(**kwargs)
    if 'ccdid' not in SRC:
        Src.ccdid = coords['chip_id']
    Src.x = coords['x']              # sky pixels
    Src.y = coords['y']              # sky pixels
    Src.theta = coords['theta']      # arcmin
    Src.phi = coords['phi']          # deg
    Log.debug('dmcoords output: %s' % str(coords))

###################################################################################
@task()
@depends(depends=[SRC[x] for x in ('ra', 'dec')],
         targets=[SRC['gal_nh']])
@setenv(ciaoenv)
def set_gal_nh():
    Src.gal_nh = Ska.CIAO.colden(Src.ra, Src.dec)
    Log.verbose('Got colden = %.2f' % Src.gal_nh)

###################################################################################
@task()
@depends(depends=[SRC[x] for x in ('theta', 'phi', 'z')],
         targets=[SRC[x] for x in ('src_rad', 'excl_rad', 'src_rad_ecf', 'excl_rad_ecf')])
@setenv(ciaoenv)
def get_apphot_ecf_rad():
    ecf_kwargs = dict(energy=Cfg.psf_energy,
                      theta=Src.theta, phi=Src.phi)
    
    Log.verbose('Calculating apertures for theta=%.2f arcmin phi=%.1f degrees energy=%.2f keV'
             % (Src.theta, Src.phi, Cfg.psf_energy))
    for par, size, unit in (('src_rad', Cfg.aperture_size, Cfg.aperture_unit),
                            ('excl_rad', Cfg.excl_rad_ecf, 'ecf')):
        if unit in ('pixel', 'kpc'):
            plate_scale = (1 / cosmocalc.cosmocalc(Src.z)['PS_kpc'] if unit == 'kpc'
                           else Cfg.arcsec_per_pixel)
            rad_arcsec = size * plate_scale
            ecf = Chandra.ECF.ECF_radius(rad_arcsec, **ecf_kwargs)
        elif unit == 'ecf':
            ecf = size
            rad_arcsec = Chandra.ECF.interp_ECF(ecf=size, **ecf_kwargs)
        else:
            raise ValueError('Unknown aperture unit "%s"' % unit)

        rad_pix = rad_arcsec / Cfg.arcsec_per_pixel

        # If radius is below allowed min then adjust
        if rad_pix < Cfg.min_src_rad:
            Log.info('Extraction radius %.2f pixels too small - setting to %.2f' %
                     (rad_pix, Cfg.min_src_rad))
            rad_pix = Cfg.min_src_rad
            rad_arcsec = rad_pix * Cfg.arcsec_per_pixel
            ecf = Chandra.ECF.ECF_radius(rad_arcsec, **ecf_kwargs)
                     
        # Convert from arcsec to pixels and require that radius >= Cfg.min_src_rad
        Src[par] = rad_pix
        Src[par + '_ecf'] = ecf

        Log.verbose("%s aperture_size=%.2f (%s) radius=%.2f pixels ecf=%.2f"
                    % (par, size, unit, rad_pix, ecf))

###################################################################################
@task()
@depends(depends=[SRC[x] for x in ('src_rad', 'excl_rad', 'x', 'y')],
         targets=[FILE['src.reg'],
                  FILE['bkg.reg'],
                  FILE['cut.reg'],
                  SRC['ann_r0'],
                  SRC['ann_r1']])
@setenv(ciaoenv)
def make_apphot_reg_files(excl_srcs=None):
    """Make CIAO region files for aperture photometry

    :param excl_srcs: recarray of detected sources that should be removed from regions
    :returns: None
    """
    src_rad = Src.src_rad
    excl_rad = Src.excl_rad
    Log.debug('Src, excl ECF radius is %.2f, %.2f' % (src_rad, excl_rad))

    # Background annulus radii
    Src.ann_r0 = excl_rad * Cfg.bkg_ann_mul0
    Src.ann_r1 = excl_rad * Cfg.bkg_ann_mul1

    # Stupidly slow but use this for now until a persistent dmcoords interface is written
    sky_coords = []
    for chipx, chipy in [(8,8), (8,1016), (1016,1016), (1016,8)]:
        Log.verbose("Running dmcoords for chip = (acis-%d, %d, %d)" %
                  (Src.ccdid, chipx, chipy))
        coords = Ska.CIAO.dmcoords(evtfile=File['ccd_evt.fits'],
                                   asolfile='@' + File['obs_asol.lis'],
                                   pos=[Src.ccdid, chipx, chipy], coordsys='chip')
        sky_coords.extend([coords['x'], coords['y']])

    chip_reg = "polygon(%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f)" % tuple(sky_coords)
    Log.debug('Determined chip region %s' % chip_reg)

    # Distance from source to excl_srcs in pixels.
    if excl_srcs is not None:
        dists = Ska.astro.sph_dist(Src.ra, Src.dec, excl_srcs.ra, excl_srcs.dec) * 3600 / 0.492

    def make_reg_file(filename, region_str, r0=None, r1=None, excl_srcs=None):
        if os.path.exists(filename):
            return
        Log.verbose("Creating region file %s" % filename)
        region = "# Region file format: CIAO version 1.0\n";
        region += "%s*%s" % (chip_reg, region_str)

        if excl_srcs is not None:
            # Exclude sources from the excl_srcs list which are not consistent with
            # Src position (first test) and are touching Src region (second test)
            bad = (dists > r0) & (dists < r1)

            # Create exclusion regions for each source within the source circle
            for excl_src in excl_srcs[bad]:
                try:
                    coords = dict(x = excl_src['x'], y = excl_src['y'])
                except IndexError:      # numpy throws IndexError not KeyError in this case
                    Log.verbose("Calculating sky x,y for excluded source at RA, dec = %.4f, %.4f" %
                             (excl_src['ra'], excl_src['dec']))
                    coords = Ska.CIAO.dmcoords(evtfile=File['ccd_evt.fits'],
                                               asolfile='@' + File['obs_asol.lis'],
                                               pos=[excl_src['ra'], excl_src['dec']], coordsys='cel')
                region += "-circle(%.2f,%.2f,%.2f)" % (coords['x'], coords['y'], excl_rad)

        Log.debug("region=\n%s" % region)
        open(filename, 'w').write(region + "\n")

    make_reg_file(File['src.reg'],
                  "circle(%.2f,%.2f,%.2f)" % (Src.x, Src.y, src_rad),
                  1+src_rad/2, src_rad+excl_rad, excl_srcs)
    make_reg_file(File['bkg.reg'],
                  "annulus(%.2f,%.2f,%.2f,%.2f)" % (Src.x, Src.y, Src.ann_r0, Src.ann_r1),
                  Src.ann_r0-excl_rad, Src.ann_r1+excl_rad, excl_srcs)
    make_reg_file(File['cut.reg'],
                  "rotbox(%.2f,%.2f,%.2f,%.2f,0)" % (Src.x, Src.y, 2*Src.ann_r1, 2*Src.ann_r1))

#####################################################################################
@task()
@depends(depends=[FILE['src.reg'],
                  FILE['bkg.reg']],
         targets=[FILE['ds9.reg']])
def make_ds9_reg_files():
    src_lines = open(File['src.reg']).readlines()
    bkg_lines = [x for x in open(File['bkg.reg']).readlines() if not x.startswith('#')]
    ds9 = open(File['ds9.reg'], 'w')
    for line in src_lines + bkg_lines:
        line = re.sub(r'\*', '\n', line)
        line = re.sub(r'-', '\n-', line)
        ds9.write(line)
    ds9.close()
    Log.verbose('Made ds9 region file %s' % File['ds9.reg'])

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['src.reg'],
                  FILE['bkg.reg'],
                  FILE['evt.fits'],
                  FILE['expmap.fits']],
         targets=[FILE['apphot.fits.gz'],
                  FILE['apphot_exp.fits.gz']])
@setenv(ciaoenv)
def calc_aperture_photom():
    bash('punlearn dmextract')
    bash("""dmextract
            infile='{{file.evt.fits}}[bin sky=@{{file.src.reg}}]'
            outfile='{{file.apphot.fits}}'
            bkg='{{file.evt.fits}}[bin sky=@{{file.bkg.reg}}]'
            error=gehrels
            bkgerror=gehrels
            opt=generic
            clobber=yes""")
    bash("""dmextract
            infile='{{file.expmap.fits}}[bin sky=@{{file.src.reg}}]'
            outfile={{file.apphot_exp.fits}}
            bkg='{{file.expmap.fits}}[bin sky=@{{file.bkg.reg}}]'
            error=gaussian
            bkgerror=gaussian
            opt=generic
            clobber=yes""")
    bash("gzip -f {{file.apphot.fits}} {{file.apphot_exp.fits}}")

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['evt.fits']],
         targets=[FILE['cut_evt.fits']])
@setenv(ciaoenv)
def make_cut_evt():
    bash("""dmcopy
            infile='{{file.evt.fits}}[sky=region({{file.cut.reg}})][{{cfg.energy_filter}}]'
            outfile='{{file.cut_evt.fits}}'
            clobber=yes""")

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['src.reg'],
                  FILE['bkg.reg']],
         targets=[FILE['src_img.reg']])
@setenv(ciaoenv)
def make_src_img_reg():
    src_reg = open(File['src.reg']).read()
    bkg_reg = open(File['bkg.reg']).read()
    open(File['src_img.reg'], 'w').write(src_reg + bkg_reg)
    Log.verbose('Created src_img_reg file %s' % File['src_img.reg'])

#####################################################################################
def _make_cut_img(infile, filetype, outfits, outjpg, regfile):
    """Make cutout images (FITS and jpg).  This gets used by subsequent tasks."""
    VAL.update(dict(x0 = "%.1f" % (Src.x - Src.ann_r1),
                    x1 = "%.1f" % (Src.x + Src.ann_r1),
                    y0 = "%.1f" % (Src.y - Src.ann_r1),
                    y1 = "%.1f" % (Src.y + Src.ann_r1),
                    bin_evt = "%.6f" % (Src.ann_r1 * 2 / Cfg.sizefits),
                    bin_img = "%f" % (Src.ann_r1 * 2 / Cfg.sizefits),
                    bin_jpg = "%.6f" % (Src.ann_r1 * 2 / Cfg.sizejpg),
                    infile = infile,
                    outfits = outfits,
                    outjpg = outjpg,
                    regfile = regfile
                    ))

    # Make output FITS image covering the size on the sky (x0:x1,y0:y1) with sizefits**2 pixels
    if filetype == 'event':
        bash("""dmcopy
             infile='{{val.infile}}[bin x={{val.x0}}:{{val.x1}}:#{{cfg.sizefits}},y={{val.y0}}:{{val.y1}}:#{{cfg.sizefits}}]'
             outfile='{{val.outfits}}'
             clobber=yes verbose=0""")
        Val['tmp_infile'] = outfits

    else:
        bash("""dmregrid
             infile={{val.infile}}
             outfile={{val.outfits}}
             bin='{{val.x0}}:{{val.x1}}:{{val.bin_img}},{{val.y0}}:{{val.y1}}:{{val.bin_img}}'
             coord_sys=physical
             rotangle=0 rotxcenter=0 rotycenter=0
             xoffset=0 yoffset=0
             npts=0
             clobber=yes verbose=0""")
        Val['tmp_infile'] = infile

    # Make temporary FITS image covering size on sky with sizejpg**2 pixels
    bash("""dmregrid
         infile='{{val.tmp_infile}}'
         outfile='{{val.outfits}}.tmp'
         bin='{{val.x0}}:{{val.x1}}:{{val.bin_jpg}},{{val.y0}}:{{val.y1}}:{{val.bin_jpg}}'
         coord_sys=physical
         rotangle=0 rotxcenter=0 rotycenter=0
         xoffset=0 yoffset=0
         npts=0
         clobber=yes verbose=0""")

    # Convert to jpeg
    bash("""dmimg2jpg
         infile='{{val.outfits}}.tmp'
         outfile={{val.outjpg}}
         regionfile='region({{val.regfile}})'
         greenfile=none bluefile=none
         showaimpoint=no showgrid=no
         scalefunction=lin
         invert=yes
         clobber=yes""")

    os.unlink(Val['outfits'] + '.tmp')

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['cut_evt.fits'],
                  FILE['src_img.reg']],
         targets=[FILE['src_img.fits'],
                  FILE['src_img.jpg']])
@setenv(ciaoenv)
def make_src_img():
    _make_cut_img(File['cut_evt.fits'], 'event', File['src_img.fits'],
                  File['src_img.jpg'], File['src_img.reg'])
    Log.verbose('Made src_img file %s' % File['src_img.jpg'])

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['expmap.fits'],
                  FILE['src_img.reg']],
         targets=[FILE['expmap_cut.fits'],
                  FILE['expmap_cut.jpg']])
@setenv(ciaoenv)
def make_expmap_cut_img():
    _make_cut_img(File['expmap.fits'], 'image', File['expmap_cut.fits'],
                  File['expmap_cut.jpg'], File['src_img.reg'])
    Log.verbose('Made expmap_cut_img file %s' % File['expmap_cut.jpg'])

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['bkg.reg']],
         targets=[FILE['fill.reg']])
def make_fill_reg():
    bkg = open(File['bkg.reg']).read()
    fill = open(File['fill.reg'], 'w')

    # Include each excluded circular region from background file to be filled
    re_xsrc = re.compile(r'- \s* ( circle\( [^)]+ \) )', re.VERBOSE)
    for xsrc in re_xsrc.finditer(bkg):
        print >>fill, xsrc.group(1)

    # Fill any region outside the polygon region which defines the chip area
    re_poly = re.compile(r'polygon \( [^)]+ \)', re.VERBOSE)
    try:
        poly = re_poly.search(bkg).group()
    except AttributeError:
        Log.error('Could not find polygon in region file')
        sys.exit(1)
    print >>fill, '!%s' % poly
    fill.close()
    Log.verbose('Made fill.reg file %s' % File['fill.reg'])

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['bkg.reg'],
                  FILE['fill.reg'],
                  FILE['src_img.fits']],
         targets=[FILE['fill_img.fits']])
@setenv(ciaoenv)
def make_fill_img():
    bash("punlearn dmfilth")
    bash("""dmfilth
         infile={{file.src_img.fits}}
         outfile={{file.fill_img.fits}}
         method=DIST
         srclist=@{{file.fill.reg}}
         bkglist=@{{file.bkg.reg}}
         clobber=yes""")

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['cut.reg'],
                  FILE['bkg.reg'],
                  FILE['fill.reg'],
                  FILE['src_img.reg'],
                  FILE['expmap.fits']],
         targets=[FILE['expmap_fill.fits']])
@setenv(ciaoenv)
def make_expmap_fill():
    tmp1 = tempfile.NamedTemporaryFile()
    tmp2 = tempfile.NamedTemporaryFile()
    bash("""dmcopy
         infile='{{file.expmap.fits}}[sky=region({{file.cut.reg}})]'
         outfile=%s
         clobber=yes""" % tmp1.name)
    bash("punlearn dmfilth")
    bash("""dmfilth
         infile=%s
         outfile=%s
         method=DIST
         srclist=@{{file.fill.reg}}
         bkglist=@{{file.bkg.reg}}
         clobber=yes""" % (tmp1.name, tmp2.name))
    _make_cut_img(tmp2.name, 'image', File['expmap_fill.fits'],
                  File['expmap_fill.jpg'], File['src_img.reg'])
    Log.verbose('Made expmap_fill_img file %s' % File['expmap_fill.jpg'])

#####################################################################################
@task()
@chdir(FILE['src_dir'])
@depends(depends=[FILE['apphot.fits.gz'],
                  FILE['apphot_exp.fits.gz']],
         targets=[FILE['apphot.pickle'],
                  FILE['apphot_exp.pickle'],
                  SRC['src_area']])
def write_apphot_pickle():
    for name in ('apphot', 'apphot_exp'):
        rows = Ska.Table.read_table(name + '.fits.gz')
        pickle.dump(rows, open(name + '.pickle', 'w'))
        Src.src_area = rows[0]['AREA']
        Log.verbose('Wrote %s.pickle' % name)

#####################################################################################
@task()
@depends(depends=[SRC['src_area']],
         targets=[SRC['src_area_ratio']])
def set_src_area_ratio():
    nom_area = math.pi * Src.src_rad**2
    Src.src_area_ratio = Src.src_area / nom_area
    Log.verbose("Set Src.src_area_ratio = %.3f" % Src.src_area_ratio)

#####################################################################################
@task(always=True)
@chdir(FILE['src_dir'])
@depends(depends=[FILE['index_template.html']],
         targets=[FILE['index.html']])
def make_index_html():
    index_html = render(open(File['index_template.html']).read())
    open(File['index.html'], 'w').write(index_html)
    Log.verbose('Created report page %s' % File['index.hmtl'])

#####################################################################################
# Main processing loop
#####################################################################################

srcs = Ska.Table.read_table(opt.objlist)
excl_srcs = Ska.Table.read_table(opt.excllist)

for src in Ska.Numpy.filter(srcs, opt.filters):
    # Clear the SRC contextdict and then populate from objlist table rows
    SRC.clear()
    for col in srcs.dtype.names:
        try:
            Src[col] = src[col].tolist()
        except AttributeError:
            Src[col] = src[col]
    pos = Ska.astro.Equatorial(Src.ra, Src.dec)
    pos.delim = ''
    Src.xdat_id = re.sub(r'\..*', '', pos.ra_hms) + re.sub(r'\..*', '', pos.dec_dms) 
    print Src.ra, type(Src.ra), Src['ra']
    Src.xdat_id = "%.4f_%.4f" % (Src.ra, Src.dec)

    pyyaks.task.start(message='Processing for %s obsid=%d ccdid=%d' % (Src['xdat_id'], Src['obsid'], Src['ccdid']))

    restore_src(File['info.pickle'])

    # Make initial directories
    make_xdat_and_src_dirs()

    # Copy/link various data files
    make_xdat_to_src_link()
    copy_resources()
    get_ccd_evt_fits()
    get_ccd_expmap_fits()
    get_evt_fits()
    get_expmap_fits()
    get_obs_asol_files()

    # Gather some numbers
    print repr(SRC['ra']), SRC['ra'].mtime, Src.ra, type(Src.ra), Src['ra']
    set_coords()
    set_gal_nh()
    get_apphot_ecf_rad()

    # Extraction processing
    make_apphot_reg_files(excl_srcs)
    make_ds9_reg_files()
    calc_aperture_photom()
    make_cut_evt()
    make_src_img_reg()
    make_src_img()
    make_expmap_cut_img()
    make_fill_reg()
    make_fill_img()
    make_expmap_fill()
    write_apphot_pickle()
    set_src_area_ratio()

    # Source report page
    make_index_html()
    
    store_src(File['info.pickle'])
    
    pyyaks.task.end(message='Processing for %s obsid=%d ccdid=%d' % (Src['xdat_id'], Src['obsid'], Src['ccdid']))

