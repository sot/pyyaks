#!/usr/bin/env python
"""
Extract photometry information from a subsample of a source list.
"""

import os
import sys

import ParseTable
from os.path import join
import yaml
import numpy
from pprint import pprint, pformat
import Ska.Table
import Ska.Numpy
import cPickle as pickle
import ContextValue

def get_options():
    from optparse import OptionParser
    parser = OptionParser()
    parser.set_defaults()
    parser.add_option("--infile",
                      default = 'sources/sdss_gal_stack0.dat',
                      help="Input source list")
    parser.add_option("--outfile",
                      help="Output photometry file")
    parser.add_option("--nhcorrfile",
                      default="nh_flux_corr.dat",
                      help="File of flux correction versus Galactic N_H")
    parser.add_option("--extracol",
                      dest = 'extracols',
                      default=[],
                      action='append',
                      help="Extra columns from source list to include in output")
    parser.add_option("--filter",
                      dest = 'filters',
                      default=[],
                      action='append',
                      help="Filter expression")
    parser.add_option('--srcdir',
                      help='Src directory expression for RA, dec, obsid, ccdid',
                      default='data/%.4f_%.4f/obs%d/ccd%d')
    (opt, args) = parser.parse_args()
    return (opt, args)

def write_ascii_table(filename, rows, sep='\t'):
    """Simple routine to write a numpy.rec.array 'rows' as an ASCII table to
    'filename'.  No quoting or escaping is done so using sep=' ' is not
    recommended.

    @param filename: File name
    @param rows: Numpy record array of table rows
    @param sep: Column separator
    """
    colnames = rows.dtype.names
    out = open(filename, 'w')
    print >>out, sep.join(colnames)
    for row in rows:
        print >>out, sep.join(str(row[x]) for x in colnames)
    out.close()

def read_info_files(infile, srcdir_expr):
    """
    Read input source list from infile, then read the corresponding info.yml
    files in each processed directory to assemble a final recarray with all
    columns from processing.
    """
    sources = ParseTable.parse_table(infile)
    info_records = []
    for source in sources:
        xdat_id = '%.4f_%.4f' % (source['ra'], source['dec'])
        srcdir = srcdir_expr % (source['ra'], source['dec'], source['obsid'], source['ccdid'])
        try:
            info = pickle.load(open(join(srcdir, 'info.pickle')))
        except IOError:
            print >>sys.stderr, 'No source info in ' + srcdir
            continue

        info['srcdir'] = srcdir
        try:
            if set(info_colnames) != set(info):
                print >>sys.stderr, 'Column mismatch in %s' % info_file
                continue
        except NameError:
            try:
                info_colnames = sorted(info)
            except:
                print type(info)
                print info
                raise

        info_records.append(tuple(info[x].val for x in info_colnames))

    return numpy.rec.fromrecords(info_records, names=info_colnames)

def main():
    opt, args = get_options()
    outcols = 'xdat_id obsid ccdid ra dec redshift exposure C_s C_b A_s A_b area_s area_b log_nh corr_nh'.split()
    outcols = outcols + opt.extracols

    if opt.outfile:
        outfile = open(opt.outfile, 'w')
    else:
        outfile = sys.stdout
    print >>outfile, " ".join(outcols)
    print >>outfile, '# %s: %s' % ('infile', opt.infile)
    for filt in opt.filters:
        print >>outfile, '# %s: %s' % ('filter', filt)

    corr_nh = Ska.Table.read_ascii_table(opt.nhcorrfile)
    sources = read_info_files(opt.infile, opt.srcdir)

    for source in Ska.Numpy.filter(sources, opt.filters):
        srcdir = source['srcdir']
        vals = {}
        for valtype in ('apphot', 'apphot_exp'):
            root = join(str(srcdir), valtype)
            vals[valtype] = pickle.load(open(root + '.pickle'))

        lognh = numpy.log10(source['gal_nh']) + 22

        out = dict()
        out['xdat_id'] = '%-18s' % source['xdat_id']
        out['obsid'] = '%5d' % source['obsid']
        out['ccdid'] = '%5d' % source['ccdid']
        out['ra'] = '%12.5f' % source['ra']
        out['dec'] = '%12.5f' % source['dec']
        out['redshift'] = '%10.5f' % source['z']
        out['exposure'] = '%12.1f' % vals['apphot'][0]['EXPOSURE']
        out['C_s'] = '%6d' % vals['apphot'][0]['COUNTS']
        out['C_b'] = '%6d' % vals['apphot'][0]['BG_COUNTS']
        out['A_s'] = '%14.1f' % vals['apphot_exp'][0]['COUNTS']
        out['A_b'] = '%14.1f' % vals['apphot_exp'][0]['BG_COUNTS']
        out['area_s'] = '%12.1f' % vals['apphot_exp'][0]['AREA']
        out['area_b'] = '%12.1f' % vals['apphot_exp'][0]['BG_AREA']
        out['log_nh'] = '%.3f' % lognh
        out['corr_nh'] = '%.3f' % (Ska.Numpy.interpolate(corr_nh['fluxcorr'], corr_nh['lognh'], [lognh]))[0]
        out.update((x, str(source[x])) for x in opt.extracols)

        print >>outfile, " ".join(out[col] for col in outcols)

    outfile.close()

if __name__ == '__main__':
    main()
