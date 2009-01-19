"""Contains classes that wrap around reading and parsing a DS game image.

`construct` is used to do the parsing, so there are a lot of its `Container`
objects used when no extra functionality is required.  Please see the source
code for lists of fields; `construct`'s field definitions are essentially
self-documenting, and I can hardly document all the fields when I don't know
myself what many of them do.
"""

from construct import *

# DS uses UTF-16 null-terminated strings for a lot of text
def UnicodeDSString(name, length, *args, **kwargs):
    kwargs.setdefault('encoding', 'utf-16')
    kwargs.setdefault('padchar', '\x00')
    return String(name, length, *args, **kwargs)

# http://www.bottledlight.com/ds/index.php/FileFormats/NDSFormat
nds_image_struct = Struct('nds_image',
    String('title', 12),
    String('id', 4),
    ULInt16('publisher_code'),
    ULInt8('unit_code'),
    ULInt8('device_code'),
    ULInt8('card_size'),
    String('card_info', 10),
    ULInt8('flags'),

    ULInt32('arm9_source'),
    ULInt32('arm9_execute_addr'),
    ULInt32('arm9_copy_to_addr'),
    ULInt32('arm9_binary_length'),
    ULInt32('arm7_source'),
    ULInt32('arm7_execute_addr'),
    ULInt32('arm7_copy_to_addr'),
    ULInt32('arm7_binary_length'),

    ULInt32('file_table_offset'),
    ULInt32('file_table_length'),
    ULInt32('fat_offset'),
    ULInt32('fat_length'),

    ULInt32('arm9_overlay_source'),
    ULInt32('arm9_overlay_length'),
    ULInt32('arm7_overlay_source'),
    ULInt32('arm7_overlay_length'),

    ULInt32('register_read_flags'),
    ULInt32('register_init_flags'),

    ULInt32('banner_offset'),
    ULInt16('crc16'),
    ULInt16('rom_timeout'),
    ULInt32('arm9_unk_offset'),
    ULInt32('arm7_unk_offset'),
    ULInt64('unenc_magic_number'),
    ULInt32('rom_length'),
    ULInt32('header_length'),

    String('unknown5', 56),
    String('gba_logo', 156),
    ULInt16('logo_crc16'),
    ULInt16('header_crc16'),
    String('reserved1', 160),
)

# http://devkitpro.cvs.sourceforge.net/viewvc/devkitpro/tools/nds/ndstool/source/ndsextract.cpp?view=markup
# To summarize how this works:
# The filename table consists of two parts.  First is a list of header rows,
# one for each directory, with the first being the root.  Each of these
# contains a (relative!) offset into the next section, pointing to a list of
# filenames contained in that directory and ending with an empty filename.
# Filenames that are directories are also followed by a directory id, which
# corresponds to a parent id in the header row.  Put this all together and it
# is possible to reconstruct the directory tree.
# Note that, since this construct uses Pointers and the offsets are relative,
# we must parse this with a stream that BEGINS at the start of the file table.
filename_list_struct = RepeatUntil(
    lambda obj, ctx: obj.metadata.length == 0,
    Struct('filenames',
        BitStruct('metadata',
            Flag('is_directory'),
            BitField('length', 7),
        ),
        MetaField('filename', lambda ctx: ctx['metadata'].length),

        # directory_id is MISSING, NOT BLANK, for non-directories
        Switch('directory_id',
            lambda ctx: ctx['metadata'].is_directory,
                { True: ULInt16('') },
            default = Pass
        )
    )
)
# The entries in this table are all the same format, but the parent_id field in
# the first entry is actually the total number of entries.  Lame.  So we treat
# it as a header row followed by however many other rows.
filename_table_struct = Struct('filename_table',
    Struct('root_directory',
        ULInt32('offset'),
        ULInt16('top_file_id'),
        ULInt16('directory_count'),
        Pointer(lambda ctx: ctx['offset'], filename_list_struct),
    ),
    MetaRepeater(
        # -1 is because the count includes the header row
        lambda ctx: ctx['root_directory'].directory_count - 1,
        Struct('directories',
            ULInt32('offset'),
            ULInt16('top_file_id'),
            ULInt16('parent_directory_id'),
            Pointer(lambda ctx: ctx['offset'], filename_list_struct),
        )
    ),
)

# http://www.bottledlight.com/ds/index.php/FileFormats/NDSFormat
banner_struct = Struct('banner',
    ULInt16('version'),
    ULInt16('crc16'),
    String('reserved1', 28),
    String('tile_data', 512),
    String('palette', 32),

    UnicodeDSString('title_jp', 256),
    UnicodeDSString('title_en', 256),
    UnicodeDSString('title_fr', 256),
    UnicodeDSString('title_de', 256),
    UnicodeDSString('title_it', 256),
    UnicodeDSString('title_es', 256),
)


class DSFile(object):
    """Represents a file inside a Nintendo DS game image.
    
    Doesn't do a lot at the moment.  So far, each one has `path` and `filename`
    property tacked on when they're created by a DSImage, but that's all.
    """

    # Laaaazy introspection
    def __str__(self):
        return str(self.__dict__)

class DSImage(object):
    """Represents a Nintendo DS game image."""
    
    def __init__(self, filename):
        """Loads the named file, parsing out some useful header information."""

        self._file = file(filename, 'rb')

        ### Load header
        self._file.seek(0)
        self._header = nds_image_struct.parse_stream(self._file)

        ### Load banner
        self._file.seek(self.header.banner_offset)
        self._banner = banner_struct.parse_stream(self._file)

        ### Construct a list of files
        self._file.seek(self.header.file_table_offset)
        # Need to grab the right number of bytes here; table contains relative
        # offsets, so the construct is much simplified when it starts at 0
        filename_table = self._file.read(self.header.file_table_length)
        tbl = filename_table_struct.parse(filename_table)

        # tbl is now a construct of varyingly useful and not-so-much data;
        # let's turn it into a tree
        dir_id = 0  # Root dir is 0, and ids are sequential after that
        seen_dirs = { 0: '' }
        self._files = []

        directories = [ tbl.root_directory ]
        directories.extend(tbl.directories)
        for dir in directories:
            dir_path = seen_dirs[dir_id]

            for filename in dir.filenames:
                if filename.filename == '':
                    # Dummy end entry; skip
                    continue

                filename.path = dir_path + '/' + filename.filename
                if filename.metadata.is_directory:
                    seen_dirs[filename.directory_id & 0xfff] = filename.path
                else:
                    f = DSFile()
                    f.filename = filename.filename
                    f.path = filename.path
                    self._files.append(f)

            dir_id += 1

    @property
    def header(self):
        """A struct of the standard DS header."""
        return self._header

    @property
    def banner(self):
        """A struct of the standard DS banner, containing a raw bitmap of the
        game's icon and titles in various languages."""
        return self._banner

    @property
    def files(self):
        """An array of files contained within the game image.
        
        Each file is a DSFile object.
        """
        return self._files
