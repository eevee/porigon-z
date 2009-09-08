import binascii
from optparse import OptionParser
import os
import pkg_resources
import re
import shutil
from sys import argv, exit, stderr, stdout

from nds import DSImage
from porigonz.nds.util.text import CharacterTable
from porigonz.nds.util.sprites import Palette, Sprite

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


def _format_raw(chunk):
    return chunk

def _format_hex(chunk):
    return binascii.hexlify(chunk)

def _format_pokemon_text(chunk):
    # LoadingNOW is awesome.
    # XXX cache this
    stream = pkg_resources.resource_stream('porigonz', 'data/pokemon.tbl')
    tbl = CharacterTable.from_stream(stream)

    strings = tbl.pokemon_translate(chunk)
    return "\n".join(strings)

def _format_pokemon_sprite(chunk):
    if not chunk:
        return ''
    elif len(chunk) <= 100:
        return Palette(chunk).png()
    else:
        return Sprite.from_pokemon(chunk).png()

formats = {}
formats['raw'] = _format_raw
formats['hex'] = _format_hex
formats['pokemon-text'] = _format_pokemon_text
formats['pokemon-sprite'] = _format_pokemon_sprite


def command_cat(image, args):
    parser = OptionParser()
    parser.add_option('-f', '--format', dest='format', type='choice', choices=formats.keys(), default='raw')
    parser.add_option('-s', '--split-narc', dest='splitnarc', type='choice', choices=['always', 'never', 'auto'], default='auto')
    options, (dsfilename,) = parser.parse_args(args)

    # XXX factor this out; do wildcards and ids
    matches = [dsfile for dsfile in image.dsfiles if dsfile.path == dsfilename]

    if len(matches) > 1:
        stderr.write("Multiple files matched.  Please specify by file id instead.")
        return
    dsfile = matches[0]

    # Handle narc splitting.  Whatever combination of file and options we got,
    # `chunks` should be a list for ease of the following code
    if options.splitnarc == 'never':
        split_narc = False
    elif options.splitnarc == 'always':
        split_narc = True
    else:  # auto
        split_narc = dsfile.is_narc

    # Printing one thing and printing many things works the same way, so just
    # use a list either way
    if split_narc:
        chunks = dsfile.parse_narc()
    else:
        chunks = [dsfile]

    # Output formatting
    format_chunk = formats[options.format]

    # Finally, print everything
    for chunk in chunks:
        print format_chunk(chunk)


def command_extract(image, args):
    # foo.nds extracts to foo/ by default
    # foo.game extracts to foo.game:data/ by default
    if re.match(r'\.nds$', image.filename):
        defaultdir = re.sub(r'\.nds$', image.filename, '')
    else:
        defaultdir = image.filename + ':data'

    parser = OptionParser()
    parser.add_option('-d', '--directory', dest='directory', default=defaultdir)
    parser.add_option('-f', '--format', dest='format', type='choice', choices=formats.keys(), default='raw')
    parser.add_option('-s', '--split-narc', dest='splitnarc', type='choice', choices=['always', 'never', 'auto'], default='auto')
    options, dsfiles = parser.parse_args(args)

    # XXX factor this out; do wildcards and ids
    if dsfiles:
        matches = [dsfile for dsfile in image.dsfiles if dsfile.path in dsfiles]
    else:
        matches = image.dsfiles

    # Output formatting
    format_chunk = formats[options.format]

    # Extract every file to the requested directory
    for dsfile in matches:
        # Narc splitting
        if options.splitnarc == 'never':
            split_narc = False
        elif options.splitnarc == 'always':
            split_narc = True
        else:  # auto
            split_narc = dsfile.is_narc

        dspath = dsfile.path
        if not dspath:
            # Construct a default filename
            dspath = "file%d" % dsfile.id

        print dspath, '...',
        stdout.flush()

        # dspath is probably absolute, and we need relative parts
        dspath = dspath.strip('/')

        if split_narc:
            # Split the file and write the pieces all inside a directory
            dsdir = dspath
            fsdir = os.path.join(options.directory, dsdir)

            # Delete the target if it already exists.  This *should* only
            # delete existing extracted files.  Who would have real files
            # called poke_msg.narc?
            if os.path.exists(fsdir):
                shutil.rmtree(fsdir)

            os.makedirs(fsdir)

            chunks = dsfile.parse_narc()
            for n, chunk in enumerate(chunks):
                dsfilename = unicode(n)

                # Create the file in the appropriate format
                fspath = os.path.join(fsdir, dsfilename)
                fsfile = open(fspath, 'wb')
                fsfile.write( format_chunk(chunk) )
                fsfile.close()

        else:
            # Write the entire file to a..  file
            dsdir, dsfilename = os.path.split(dspath)
            fsdir = os.path.join(options.directory, dsdir)

            if os.path.exists(fsdir):
                shutil.rmtree(fsdir)

            os.makedirs(fsdir)

            # Create the file in the appropriate format
            fspath = os.path.join(fsdir, dsfilename)
            fsfile = open(fspath, 'wb')
            fsfile.write( format_chunk(dsfile.contents) )
            fsfile.close()

        print 'ok'
