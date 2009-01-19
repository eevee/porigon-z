from sys import argv, exit

from nds import DSImage

help = """porigon-z: a Nintendo DS game image reader aimed at Pokemon
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
        for dsfile in image._files:
            print dsfile.path


