import binascii
from optparse import OptionParser
import os
from sys import argv, exit, stderr

from nds import DSImage

help = """porigon-z: a Nintendo DS game image inspector aimed at Pokemon
Syntax: porigon-z {path-to-image-file} {command} ...

Commands:
list
    List the files contained in the image.

cat [-f FORMAT] {ds-filename}
    Prints the contents of a single file within the DS image to standard out.

    -f FORMAT       Specifies the formatting to use.

Formats:
raw
    The default.  Does no processing at all; spits out raw binary.

narc
    Splits a NARC file into multiple binary chunks.

narc-hex
    Splits a NARC file into multiple hex chunks.
"""

def main():
    if len(argv) < 3:
        print help
        exit(0)

    (filename, command) = argv[1:3]
    args = argv[3:]
    image = DSImage(filename)

    func = globals().get("command_%s" % command, None)
    if func:
        func(image, args)
    else:
        print help
        exit(0)


def command_examine(image, args):
    print image.banner.title_en


def command_list(image, args):
    prev_path_parts = []

    for dsfile in image.dsfiles:
        if dsfile.path:
            path = dsfile.path

            # Print a directory header if it changed
            path_parts = path.split('/')
            path_parts.pop()  # Drop filename
            if path_parts != prev_path_parts:
                dir_path = '/'.join(path_parts)
                print dir_path
                prev_path_parts = path_parts
        else:
            path = '(no filename)'

        end = dsfile.offset + dsfile.length

        print "%(id)5d 0x%(start)08x 0x%(end)08x %(length)9d %(path)s" % {
            'id': dsfile.id,
            'start': dsfile.offset,
            'end': end,
            'length': dsfile.length,
            'path': path,
        }


def command_cat(image, args):
    parser = OptionParser()
    parser.add_option('-f', '--format', dest='format')
    options, (dsfilename,) = parser.parse_args(args)

    # XXX factor this out; do wildcards and ids
    matches = [dsfile for dsfile in image.dsfiles if dsfile.path == dsfilename]

    if len(matches) > 1:
        stderr.write("Multiple files matched.  Please specify by file id instead.")
        return

    if not options.format or options.format == 'raw':
        print matches[0].contents

    elif options.format == 'narc-hex':
        records = matches[0].parse_narc()
        for record in records:
            print binascii.hexlify(record)

    elif options.format == 'narc':
        records = matches[0].parse_narc()
        for record in records:
            print record


def command_extract(image, args):
    # XXX these should be params, via getopt
    targetdir = 'data'
    format = 'raw'

    # XXX factor this out; do wildcards and ids
    if args:
        matches = [dsfile for dsfile in image.dsfiles if dsfile.path in args]
    else:
        matches = image.dsfiles

    # Extract every file to the requested directory
    for dsfile in matches:
        dspath = dsfile.path
        if not dspath:
            # Default filename
            dspath = "file%d" % dsfile.id

        dsdir, dsfilename = os.path.split(dspath)
        # dsdir is probably absolute, and join() wants relative parts, so
        # prepend a dot
        dsdir = './' + dsdir
        fsdir = os.path.join(targetdir, dsdir)
        try:
            os.makedirs(fsdir)
        except OSError:
            # Already exists; not a problem
            pass

        # Create the file in the appropriate format
        # XXX ummm do formats
        fspath = os.path.join(fsdir, dsfilename)
        print dspath, '...',
        fsfile = open(fspath, 'wb')
        fsfile.write(dsfile.contents)
        fsfile.close()
        print 'ok'
