#!/usr/bin/env python

import os
import re
import sys
import cPickle as pickle

import yaml
import Ska.Shell
import Ska.File
import Ska.Table
import Ska.CIAO
import Chandra.ECF

import Task
import Logging as Log
import ContextValue
from ContextValue import ContextDict, ContextDictAccessor, render, render_first_arg, render_args

# Initialize output logging
loglevel = Log.DEBUG
Log.init(stdoutlevel=loglevel, filename='test.log', filelevel=loglevel, format="%(message)s")

# Create bash wrapper around Shell.bash.  This sets up a file-like object
# to stream shell pexpect output in a way that plays well with Task output.
bash = Task.bash(loglevel)

# Setup CIAO
ciaoenv = Ska.Shell.getenv('. /soft/ciao/bin/ciao.bash')
pfiles_dir = Ska.CIAO.localize_param_files(ciaoenv)

# Vars for staxx processing
input_dir = 'champ*/OBS{{src.obsid.val|stringformat:"05d"}}/XPIPE' # Input data directory glob
output_dir = 'data/xdat'                            # Output data directory
objlist = 'sources/sdss_gal_stack0.dat'	        # Object list file
excllist = 'sources/xsrclist4stackexcl.dat'      # Excluded objects file
log_file = 'staxx.log'                      # Yaxx log file or directory
evt2_glob   = 'evt2_ccdid{{src.ccdid}}.fits*'
expmap_glob = 'expmap_{{src.ccdid}}.fits*'
asol_glob   = 'pcad*_asol1.fits*'

# Define file aliases
FILE = ContextDict('file', basedir=output_dir, valuetype=ContextValue.File)
FILE.update(dict(
    obs_dir =       'obs{{src.obsid}} / '
    obs_asol =      'obs{{src.obsid}} / asol'
    ccd_dir =       'obs{{src.obsid}} / ccd{{src.ccdid}} /'
    ccd_evt =       'obs{{src.obsid}} / ccd{{src.ccdid}} / acis_evt2'
    ccd_expmap =    'obs{{src.obsid}} / ccd{{src.ccdid}} / expmap'
    ccd_src_dir =   'obs{{src.obsid}} / ccd{{src.ccdid}} / x{{src.xdat_id}}'
    src_dir =       'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / '
    asol =          'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / asol'
    evt =           'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / acis_evt2'
    cut_evt =       'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / acis_cut_evt2'
    expmap =        'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / expmap'
    expmap_cut =    'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / expmap_cut'
    expmap_filled = 'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / expmap_fill'
    src =           'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / src'
    bkg =           'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / bkg'
    cut =           'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / cut'
    fill =          'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / fill'
    ds9 =           'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / ds9'
    apphot =        'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / apphot'
    apphot_exp =    'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / apphot_exp'
    cut_img =       'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / acis_cut_img'
    fill_img =      'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / acis_fill_img'
    info =          'x{{src.xdat_id}} / obs{{src.obsid}} / ccd{{src.ccdid}} / info'))
File = ContextDictAccessor(FILE)

# Define src vars
SRC = ContextDict('src')
SRC.format.update(dict(ra='%.4f',
                       dec='%.4f'))
Src = ContextDictAccessor(SRC)

# Configuration values
CFG = ContextDict('cfg')
CFG.update(dict(energy_filter = 'energy=500:7000',
                psf_fraction = 0.9,               # enclosed cts frac for aperture photom
                psf_energy = 1.5,                 # kev
                min_src_rad = 4,
                bkg_ann_mul0 = 2.0,
                bkg_ann_mul1 = 7.0))
Cfg = ContextDictAccessor(CFG)

# Set up a couple of functions for convenience
get_globfiles = render_args(Ska.File.get_globfiles)
make_local_copy = render_args(Ska.File.make_local_copy)

def vars_in(contextdict, *vars):
    return all(var in contextdict for var in vars)

#####################################################################################
# Task definitions
#####################################################################################
@render_first_arg
def make_dir(dir_):
    """Make a directory if it doesn't exist."""
    if not os.path.isdir(dir_):
        os.makedirs(dir_)
        if not os.path.isdir(dir_):
            raise Task.TaskFailure('Failed to make directory %s' % dir_)
        Log.verbose('Made directory ' + dir_)
        
###################################################################################
@Task.task()
def make_xdat_and_src_dirs():
    make_dir(File['src_dir'])
    make_dir(File['ccd_dir'])

###################################################################################
@Task.task(dir=File['ccd_dir'])
def make_xdat_to_src_link():
    if not os.path.exists(File['ccd_src_dir'].rel):
        os.symlink(File['src_dir'].rel, File['ccd_src_dir'].rel)

###################################################################################
@Task.task()
def restore_object_data(filename, obj):
    filename = render(filename)
    Log.verbose('Restoring from %s' % filename)
    if os.path.exists(filename):
        obj.update(yaml.load(open(filename)))

###################################################################################
@Task.task()
def store_object_data(filename, obj):
    filename = render(filename)
    Log.verbose('Storing to %s' % filename)
    yaml.dump(obj, open(filename, 'w'))

###################################################################################
@Task.task()
def restore_src(filename):
    Log.verbose('Restoring from %s' % filename)
    if os.path.exists(filename):
        Src.update(pickle.load(open(filename, 'r')))
        
###################################################################################
@Task.task()
def store_src(filename):
    Log.verbose('Storing to %s' % filename)
    pickle.dump(Src, open(filename, 'w'))

@Task.task(targets=(FILE['ccd_evt.fits'],
                    FILE['evt.fits'],
                    FILE['ccd_expmap.fits'],
                    FILE['expmap.fits']))
def get_evt_expmap_files():
    f = get_globfiles(os.path.join(input_dir, evt2_glob))[0]
    make_local_copy(f, File['ccd_evt.fits'], linkabs=True)
    make_local_copy(File['ccd_evt.fits'], File['evt.fits'])

    f = get_globfiles(os.path.join(input_dir, expmap_glob))[0]
    make_local_copy(f, File['ccd_expmap.fits'], linkabs=True)
    make_local_copy(File['ccd_expmap.fits'], File['expmap.fits'])


###################################################################################
@Task.task()
def get_obs_asol_files():
    files = get_globfiles(os.path.join(input_dir, asol_glob), maxfiles=None)
    obs_copies = [File['obs_asol'].rel + '_%d.fits' % i for i in range(len(files))]
    for f, l in zip(files, obs_copies):
        make_local_copy(f, l)
    obs_copies_base = [os.path.basename(x) for x in obs_copies]
    open(File['obs_asol.lis'].rel, 'w').write('\n'.join(obs_copies_base))

###################################################################################
@Task.task(depends=[FILE['ccd_evt.fits'],
                    FILE['obs_asol.lis'],
                    (vars_in, (SRC, 'ra', 'dec'), {})],
           targets=[(vars_in, (SRC, 'x', 'y', 'ccd_id', 'theta', 'phi'), {})],
           env=ciaoenv)
def set_coords():
    coords = Ska.CIAO.dmcoords(evtfile=File['ccd_evt.fits'].rel,
                               asolfile='@' + File['obs_asol.lis'].rel,
                               pos=[Src['ra'].val, Src['dec'].val], coordsys='cel')
    Src['ccd_id'] =coords['chip_id']
    Src['x'] = coords['x']              # sky pixels
    Src['y'] = coords['y']              # sky pixels
    Src['theta'] = coords['theta']      # arcmin
    Src['phi'] = coords['phi']          # deg

###################################################################################
@Task.task(depends=[(vars_in, (SRC, 'ra', 'dec'), {})],
           targets=[(vars_in, (SRC, 'gal_nh'), {})],
           env=ciaoenv)
def set_gal_nh():
    Src['gal_nh'] = Ska.CIAO.colden(Src['ra'].val, Src['dec'].val)


###################################################################################
@Task.task(depends=[(vars_in, (CFG, 'psf_fraction', 'psf_energy'), {}),
                    (vars_in, (SRC, 'theta', 'phi'), {})],
           targets=[(vars_in, (SRC, 'src_rad', 'excl_rad'), {})],
           env=ciaoenv)
def get_apphot_ecf_rad():
    for par, psffrac in (('src_rad', Cfg['psf_fraction'].val),
                         ('excl_rad', 0.90)):
        rad = Chandra.ECF.interp_ECF(ecf=psffrac, energy=Cfg['psf_energy'].val,
                                     theta=Src['theta'].val, phi=Src['phi'].val,
                                     shape='circular', value='radius')
        Src[par] = rad / 0.492            # Convert arcsec to ACIS pixels
        Log.verbose("Extraction radius (%.0f%%) is %.2f pixels for (theta,phi)=(%.2f',%.1f deg)" %
                    (psffrac * 100, Src[par].val, Src['theta'].val, Src['phi'].val))

###################################################################################
@Task.task(depends=[(vars_in, (CFG, 'min_src_rad', 'bkg_ann_mul0', 'bkg_ann_mul1'), {}),
                    (vars_in, (SRC, 'src_rad', 'excl_rad', 'x', 'y'), {}),
                    FILE['ccd_evt.fits'],
                    FILE['obs_asol.lis'],
                    ],
           targets=[FILE['src'],
                    FILE['bkg'],
                    FILE['cut'],
                    ],
           env=ciaoenv,
           )
def make_apphot_reg_files(excl_srcs):
    """
    Make CIAO region files for aperture photometry

    :param src_file: source region file
    :param bkg_file: background region file
    :param cut_file: cutout region file
    :param excl_srcs: recarray of detected sources that should be removed from regions

    :returns: None
    """
    # Set some vars for notational convenience
    min_rad = Cfg['min_src_rad'].val
    src_rad = Src['src_rad'].val
    excl_rad = Src['excl_rad'].val
    src_x = Src['x'].val
    src_y = Src['y'].val
    src_file = File['src'].rel
    bkg_file = File['bkg'].rel
    cut_file = File['cut'].rel
    src_ccd_id = Src['ccd_id'].val

    # Force minimum source extraction radius
    src_rad = max(src_rad, min_rad)
    excl_rad = max(excl_rad, min_rad)

    Log.debug('Src, excl ECF radius is %.2f, %.2f' % (src_rad, excl_rad))

    # Background annulus radii
    Src['ann_r0'] = excl_rad * Cfg['bkg_ann_mul0'].val
    Src['ann_r1'] = excl_rad * Cfg['bkg_ann_mul1'].val

    # Stupidly slow but use this for now until a persistent dmcoords interface is written
    sky_coords = []
    for chipx, chipy in [(8,8), (8,1016), (1016,1016), (1016,8)]:
        Log.debug("Running dmcoords for chip = (acis-%d, %d, %d)" %
                  (src_ccd_id, chipx, chipy))
        coords = Ska.CIAO.dmcoords(evtfile=File['ccd_evt.fits'].rel,
                                   asolfile='@' + File['obs_asol.lis'].rel,
                                   pos=[src_ccd_id, chipx, chipy], coordsys='chip')
        sky_coords.extend([coords['x'], coords['y']])

    chip_reg = "polygon(%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f)" % tuple(sky_coords)
    Log.debug('Determined chip region %s' % chip_reg)

    if not os.path.exists(src_file):
	Log.info("Creating src.reg for source")
	regfile = open(src_file, 'w')
	region = "circle(%.2f,%.2f,%.2f)" % (src_X, src_Y, src_rad)
	region += "# Region file format: CIAO version 1.0\n";
	region += "chip_reg*src_reg"

        ok = Ska.astro.sph_dist(Src['ra'].)
        # Create exclusion regions for each source within the source circle
        for excl_src in excl_srcs:
            # Only worry about other sources in the same obsid
            if excl_src.obsid == Src['obsid'].val:
                pass
            
            # Took out this exclusion.  Discussion with PJG 2008-Sep-15.
            # && excl->{ccdid} == Src['ccdid});

            # If we don't have a sky(x,y) for the source already then get it with dmcoords.
            unless (defined excl->{X} and defined excl->{Y}) {
                print "Calculating X,Y for excl->{ra} excl->{dec}\n";
                out = self->DMcoord_coords( cel => (excl->{ra}, excl->{dec} ) );
                excl->{X} = out[0]->{sky}->{'x'};
                excl->{Y} = out[0]->{sky}->{'y'};
            }

            # Don't exclude the source itself
            next if ((src_X - excl->{X})**2 + (src_Y - excl->{Y})**2 < (1+src_rad/2)**2);

            # If it overlaps with outer radius of the annulus then print exclusion region
            if ((src_X - excl->{X})**2 + (src_Y - excl->{Y})**2 < (src_rad + excl_rad)**2) {
                exc_reg = sprintf "circle(%.2f,%.2f,%.2f)", excl->{X}, excl->{Y}, excl_rad;
                print SRC "-exc_reg";
            }
	}
        print SRC "\n";
	close SRC;
    }

##     unless (-r bkg_file) {
## 	open BKG, "> bkg_file" or do {
## 	    message(1, "ERROR - could not open bkg region bkg_file\n");
## 	    return;
## 	};

## 	print BKG "# Region file format: CIAO version 1.0\n";
## 	printf BKG ("chip_reg * annulus(%.2f,%.2f,%.2f,%.2f)",
## 		    src_X, src_Y, Src['ann_r0}, Src['ann_r1});

##         # Create exclusion regions for each source within the background annulus
## 	foreach excl (apphot_src_list) {
##             # Don't exclude the source itself
##             # next if excl->{id} == Src['id};

##             # Only worry about other sources in the same obsid and ccd
##             next unless (excl->{obsid} == Src['obsid}
##                          && excl->{ccdid} == Src['ccdid});

##             # If we don't have a sky(x,y) for the source already then get it with dmcoords.
##             unless (defined excl->{X} and defined excl->{Y}) {
##                 out = self->DMcoord_coords( cel => (excl->{ra}, excl->{dec} ) );
##                 excl->{X} = out[0]->{sky}->{'x'};
##                 excl->{Y} = out[0]->{sky}->{'y'};
##             }

##             # Don't exclude the source itself
##             next if ((src_X - excl->{X})**2 + (src_Y - excl->{Y})**2 < (1+src_rad/2)**2);

##             # If it overlaps with outer radius of the annulus then print exclusion region
##             if ((src_X - excl->{X})**2 + (src_Y - excl->{Y})**2 
##                 < (Src['ann_r1} + excl_rad)**2) {
##                 bkg_reg = sprintf "circle(%.2f,%.2f,%.2f)", excl->{X}, excl->{Y}, excl_rad;
##                 print BKG "-bkg_reg";
##             }
## 	}
##         print BKG "\n";
## 	close BKG;
##     }

##     unless (-r cut_file) {
## 	open CUT, "> cut_file" or do {
## 	    message(1, "ERROR - could not open cut region cut_file\n");
## 	    return;
## 	};
##         box_r1 = Src['ann_r1};

## 	print CUT "# Region file format: CIAO version 1.0\n";
## 	printf CUT ("rotbox(%.2f,%.2f,%.2f,%.2f,0)\n",
## 		    src_X, src_Y, box_r1 * 2.0, box_r1 * 2.0);
## 	close CUT;
##     }

##     1;
## }

#####################################################################################
# Main processing loop
#####################################################################################

srcs = Ska.Table.read_table(objlist)
for srcrow in srcs[:1]:
    for key in Src.keys():
        del Src[key]
    for col in srcs.dtype.names:
        Src[col] = srcrow[col].tolist()
    Src['xdat_id'] = render('{{src.ra}}_{{src.dec}}')

    Task.start(message='Processing for %s' % Src['xdat_id'])

    restore_src(File['info.pickle'].rel)

    make_xdat_and_src_dirs()
    make_xdat_to_src_link()
    get_evt_expmap_files()
    get_obs_asol_files()
    set_coords()
    set_gal_nh()
    get_apphot_ecf_rad()
    make_apphot_reg_files([])

    store_src(File['info.pickle'].rel)
    
    Task.end(message='Processing for %s' % Src['xdat_id'])

# hard  uses Chandra.ECF
## <process_step>
##   name         make_apphot_reg_files
##   dir          %FILE{src_dir}%
##   target_file  %FILE{src_reg}%
##   target_file  %FILE{bkg_reg}%
##   target_file  %FILE{cut}%
##   loop         band = broad
##   loop         ecf = 90
##   method       make_apphot_reg_files
## </process_step>

# easy
## <process_step>
##   name         make_ds9_reg_files
##   dir          %FILE{src_dir}%
##   depend_file  %FILE{src_reg}%
##   depend_file  %FILE{bkg_reg}%
##   target_file  %FILE{ds9_reg}%
##   loop         band = broad
##   loop         ecf = 90
##   command      <<COMMAND
##    cat %FILE{src_reg}% %FILE{bkg_reg}%
##    | sed 
##       -e 's/ \* /\n/g'
##       -e 's/ - /\n-/g'
##    > %FILE{ds9_reg}%
## COMMAND
## </process_step>

# easy
## <process_step>
##   name         calc_aperture_photom
##   dir          %FILE{src_dir}%
##   depend_file  %FILE{src_reg}%
##   depend_file  %FILE{bkg_reg}%
##   depend_file  %FILE{evt}%
##   depend_file  %FILE{expmap}%
##   target_file  %FILE{apphot.fits.gz}%
##   target_file  %FILE{apphot_exp.fits.gz}%
##   loop         band = broad
##   loop         ecf = 90
##   command      punlearn dmextract
##   command      <<COMMAND
##    dmextract
##     infile='%FILE{evt}%[bin sky=@%FILE{src_reg}%]'
##     outfile=%FILE{apphot.fits}%
##     bkg='%FILE{evt}%[bin sky=@%FILE{bkg_reg}%]'
##     error=gehrels
##     bkgerror=gehrels
##     opt=generic
##     clobber=yes
## COMMAND
##   command      <<COMMAND
##    dmextract
##     infile='%FILE{expmap}%[bin sky=@%FILE{src_reg}%]'
##     outfile=%FILE{apphot_exp.fits}%
##     bkg='%FILE{expmap}%[bin sky=@%FILE{bkg_reg}%]'
##     error=gaussian
##     bkgerror=gaussian
##     opt=generic
##     clobber=yes
## COMMAND
##   command gzip -f %FILE{apphot.fits}% %FILE{apphot_exp.fits}%
## </process_step>

# easy
## #######################################################################
## ## Make cutout event file
## #######################################################################
## <process_step>
##    name        make_cut_evt
##    dir         %FILE{src_dir}%
##    depend_file %FILE{evt}%
##    target_file %FILE{cut_evt}%
##    loop        band = broad
##    command     <<COMMAND
##     dmcopy
##      infile='%FILE{evt}%[sky=region(%FILE{cut}%)][%VALUE{energy_filter_%VALUE{band}%}%]'
##      outfile='%FILE{cut_evt}%'
##      clobber= yes 
## COMMAND
## </process_step>

# easy (or medium with modularization of make_cutout.py)
## ######################################################################
## # Make src cutout images
## ######################################################################
## <process_step>
##    name        make_src_images
##    dir         %FILE{src_dir}%
##    depend_file %FILE{cut_evt}%
##    depend_file %FILE{src}%
##    depend_file %FILE{bkg}%
##    target_file %FILE{source_image.fits}%
##    target_file %FILE{source_image.jpg}%
##    target_file %FILE{source_image.reg}%
##    loop        band = broad
##    command     cat %FILE{src}% %FILE{bkg}% > %FILE{source_image.reg}%
##    command     <<COMMAND
##     /home/aldcroft/arch/x86_64-linux_RHFC-8/bin/python /data/baffin/tom/Science/Champ/Stacking/inhxs/scripts/make_cutout.py
##      --infile   '%FILE{cut_evt}%'
##      --outfits   '%FILE{source_image.fits}%'
##      --outjpg    '%FILE{source_image.jpg}%'
##      --x         %VALUE{X}%
##      --y         %VALUE{Y}%
##      --sizesky   %VALUE{ann_r1}%
##      --sizefits  80
##      --sizejpg   300
##      --regionfile '%FILE{source_image.reg}%'
## COMMAND
## </process_step>

# easy once above is done
## ######################################################################
## # Make expmap cutout images
## ######################################################################
## <process_step>
##    name        make_expmap_images
##    dir         %FILE{src_dir}%
##    depend_file %FILE{expmap}%
##    depend_file %FILE{source_image.reg}%
##    target_file %FILE{expmap_cut.fits}%
##    target_file %FILE{expmap_cut.jpg}%
##    loop        band = broad
##    command     <<COMMAND
##     /home/aldcroft/arch/x86_64-linux_RHFC-8/bin/python /data/baffin/tom/Science/Champ/Stacking/inhxs/scripts/make_cutout.py
##      --infile   '%FILE{expmap}%'
##      --intype   image
##      --outfits   '%FILE{expmap_cut.fits}%'
##      --outjpg    '%FILE{expmap_cut.jpg}%'
##      --x         %VALUE{X}%
##      --y         %VALUE{Y}%
##      --sizesky   %VALUE{ann_r1}%
##      --sizefits  80
##      --sizejpg   300
##      --regionfile '%FILE{source_image.reg}%'
##    command     dmlist %FILE{expmap_cut.fits}% blocks
## COMMAND
## </process_step>

# easy or medium
## ######################################################################
## # Make fill region file (for filling over known x-ray sources)
## ######################################################################
## <process_step>
##    name        make_fill_region
##    dir         %FILE{src_dir}%
##    depend_file %FILE{bkg_reg}%
##    target_file %FILE{fill_reg}%
##    command     <<COMMAND
##     %FILEABS{analysis_dir}%/scripts/make_fill_reg.py
##      --infile    '%FILE{bkg_reg}%'
##      --outfile   '%FILE{fill_reg}%'
## COMMAND
## </process_step>

# easy
## ######################################################################
## # Make filled image
## ######################################################################
## <process_step>
##    name        make_filled_image
##    dir         %FILE{src_dir}%
##    depend_file %FILE{bkg_reg}%
##    depend_file %FILE{fill_reg}%
##    depend_file %FILE{source_image.fits}%
##    target_file %FILE{filled_image.fits}%
##    loop        band = broad
##    command     punlearn dmfilth
##    command     <<COMMAND
##     dmfilth
##       infile=%FILE{source_image.fits}%
##       outfile=%FILE{filled_image.fits}%
##       method=DIST
##       srclist=@%FILE{fill_reg}%
##       bkglist=@%FILE{bkg_reg}%
##       clobber=yes
## COMMAND
## </process_step>


# easy
## ######################################################################
## # Make filled exposure map
## ######################################################################
## <process_step>
##    name        make_filled_expmap
##    dir         %FILE{src_dir}%
##    depend_file %FILE{cut}%
##    depend_file %FILE{bkg_reg}%
##    depend_file %FILE{fill_reg}%
##    depend_file %FILE{expmap}%
##    target_file %FILE{expmap_filled.fits}%
##    loop        band = broad
##    command     punlearn dmfilth
##    command     <<COMMAND
##     dmcopy
##       infile='%FILE{expmap}%[sky=region(%FILE{cut}%)]'
##       outfile='%FILE{expmap_cut.fits}%tmp2'
##       clobber=yes
## COMMAND
##    command     <<COMMAND
##     dmfilth
##       infile=%FILE{expmap_cut.fits}%tmp2
##       outfile=%FILE{expmap_filled.fits}%tmp2
##       method=DIST
##       srclist=@%FILE{fill_reg}%
##       bkglist=@%FILE{bkg_reg}%
##       clobber=yes
## COMMAND
##    command     <<COMMAND
##     /home/aldcroft/arch/x86_64-linux_RHFC-8/bin/python %FILEABS{analysis_dir}%/scripts/make_cutout.py
##      --infile   %FILE{expmap_filled.fits}%tmp2
##      --intype   image
##      --outfits   %FILE{expmap_filled.fits}%
##      --outjpg    %FILE{expmap_filled.jpg}%
##      --x         %VALUE{X}%
##      --y         %VALUE{Y}%
##      --sizesky   %VALUE{ann_r1}%
##      --sizefits  80
##      --sizejpg   300
##      --regionfile '%FILE{source_image.reg}%'
## COMMAND
##     command rm %FILE{expmap_filled.fits}%tmp2 %FILE{expmap_cut.fits}%tmp2
## </process_step>

# hard??
## ######################################################################
## # Make filled exposure map
## ######################################################################
## <process_step>
##    name        write_apphot_dat_and_check_src_reg
##    dir         %FILE{src_dir}%
##    depend_file %FILE{apphot.fits.gz}%
##    depend_file %FILE{apphot_exp.fits.gz}%
##    target_file %FILE{apphot.dat}%
##    target_file %FILE{apphot_exp.dat}%
##    method      write_apphot_dat_and_check_src_reg
## </process_step>

# hard
## <process_step>
##   name         make_html_report     
##   dir           %FILE{obs_dir}%
##   always_run   1
##   depend_file   %FILE{source_image.jpg}%
##   depend_file   %FILE{report_template.html}%
##   target_file   %FILE{report.html}%
##   delete_file   %FILE{report.html}%
##   method       make_html_report     
## </process_step>

## <process_step>
##   name         store_source_information
##   always_run   1
##   method       store_object         
## </process_step>

## <process_step>
##   name         store_info_yaml
##   always_run   1
##   method       store_info_yaml
## </process_step>

