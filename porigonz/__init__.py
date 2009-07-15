import os
from sys import argv, exit, stderr

from nds import DSImage

help = """porigon-z: a Nintendo DS game image inspector aimed at Pokemon
Syntax: porigon-z {path-to-image-file} {command} ...

Commands that should work on any DS image:
    list        List the files contained in the image
"""

def main():
    if len(argv) < 3:
        print help
        exit(0)

    (filename, command) = argv[1:3]
    args = argv[3:]

    image = DSImage(filename)

    if command == 'list':
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

    elif command == 'cat':
        (dsfilename,) = args
        # XXX factor this out; do wildcards and ids
        matches = [dsfile for dsfile in image.dsfiles if dsfile.path == dsfilename]

        if len(matches) > 1:
            stderr.write("Multiple files matched.  Please specify by file id instead.")
            return

        print matches[0].contents
