# encoding: utf8
"""Handling NDS sprites."""

from collections import namedtuple
from cStringIO import StringIO
from itertools import izip

from construct import *
import png

from porigonz.nds.util import cap_to_bits, word_iterator

# Nintendo color resource; wraps palletes
nclr_struct = Struct('nclr',
    Const(Bytes('magic', 4), 'RLCN'),
    Const(Bytes('bom', 4), '\xff\xfe\x00\x01'),
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('num_sections'),
    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
)

# Palette data
ttlp_struct = Struct('ttlp',
    Const(Bytes('magic', 4), 'TTLP'),
    ULInt32('length'),
    ULInt32('bit_depth'),
    Const(ULInt32('padding'), 0),
    ULInt32('data_length'),  # XXX what?  see docs
    ULInt32('num_colors'),

    # XXX This should use some other field for length but they all seem wrong
    MetaField('data', lambda ctx: 16 * 2),
)

class Palette(object):
    """Represents a DS palette.

    After creating a palette, a list of color stored as r, g, b tuples is
    available from the colors property.
    """

    def __init__(self, chunk):
        """Parses a binary chunk as a B5 G5 R5 palette."""
        self.colors = []

        nclr = nclr_struct.parse(chunk)

        # XXX this SHOULD have two sections according to format docs.
        # ttlp.data won't leak into a following section, at least
        ttlp = ttlp_struct.parse(nclr.data)

        for palette_word in word_iterator(ttlp.data, 16):
            r = (palette_word & 0x001f)
            g = (palette_word & 0x03e0) >> 5
            b = (palette_word & 0x7c00) >> 10

            self.colors.append((r, g, b))

    def png(self):
        """Returns a PNG illustrating the colors in this palette."""

        img = [index for index in range(len(self.colors))
               for col_repeat in range(8)]
        img = [img] * 8

        writer = png.Writer(len(self.colors) * 8, 8,
                            palette=self.colors, bitdepth=5)
        buffer = StringIO()
        writer.write(buffer, img)
        return buffer.getvalue()

    def __str__(self):
        """Returns this palette as a PNG."""
        return self.png()


# Nintendo character graphic resource
rgcn_struct = Struct('rgcn',
    Const(Bytes('magic', 4), 'RGCN'),
    Bytes('bom', 4),   # \xff\xfe\x01\x01 or \xff\xfe\x00\x01
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('num_sections'),
    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
)

# "Character" data
# Most of this seems totally wrong for Pokémon
rahc_struct = Struct('rahc',
    Const(Bytes('magic', 4), 'RAHC'),
    ULInt8('header_length'), # 0x20),
    BitStruct('length',
        BitField('length', 24),
    ),
    ULInt16('num_pixels'),
    ULInt16('pixel_size'),
    ULInt32('bit_depth'),
    ULInt64('padding'),
    ULInt32('data_size'),
    ULInt32('unknown1'),
#    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
    MetaField('data', lambda ctx: 2048),  # XXX length is off by a factor of 1024??
)

Size = namedtuple('Size', ['width', 'height'])

class Sprite(object):
    """Represents a DS sprite."""

    @classmethod
    def from_standard(cls, chunk):
        """Parses a nybble-based sprite from a chunk."""

        self = cls()

        rgcn = rgcn_struct.parse(chunk)
        rahc = rahc_struct.parse(rgcn.data)

        # XXX make these less constant somehow
        self.size = Size(width=64, height=64)

        self.pixels = [[0] * self.size.width for _ in range(self.size.height)]
        for i, word in enumerate(word_iterator(rahc.data, 4)):
            x, y = self.get_pos(i, tile_size=8)
            self.pixels[y][x] = word

        return self

    @classmethod
    def from_pokemon(cls, chunk):
        """Parses a Pokémon sprite from a chunk.

        This encryption is only used for the Pokémon themselves and trainers.
        Items, berries, the map, the bag, etc. are all regular DS sprites.

        Encryption appears to be done by producing a series of 16-bit integers
        from the inverse of the Pokémon PRNG (a linear congruential generator),
        then XORing that series with the entire image, reinterpreted as 16-bit
        integers.  The game then decrypts the images by doing the same thing in
        reverse, using the first or last few pixels in the image as the seed to
        the PRNG to reproduce the same mask.
        """

        self = cls()

        rgcn = rgcn_struct.parse(chunk)
        rahc = rahc_struct.parse(rgcn.data)

        # XXX make these less constant sometime.
        # XXX and determine which constants to use.
        self.size = Size(width=160, height=80)
        # D/P
        # similarly uses a different add constant for the first block
        add = 0x61a1
        mult = 0xeb65
        # Platinum
        # These actually produce the same sequence as D/P, only backwards.  It
        # seems the encryption mask in D/P started at the beginning, so the
        # decryption had to start at the end—but some sprites in Platinum have
        # non-blank last pixels.  So they had to switch it around and have the
        # first pixel (with the same constants) be the decryption seed instead.
        # I'm always using the first pixel as the seed, thus I have different
        # constants.
        # add = 0x89c3  # appears to be the first dummy block only?
        add = 0x6073
        mult = 0x4e6d

        # Simple mask generator
        def mask_generator():
            key = (word_iterator(rahc.data[0:2], 16)).next()
            while True:
                yield key
                key = cap_to_bits(key * mult + add, 16)

        def pixel_generator():
            # Unmask the sprite data
            for word, mask in izip(word_iterator(rahc.data, 16),
                                   mask_generator()):
                unmasked = word ^ mask
                # This is 16 bits, and there are four bits per pixel, so we
                # have four pixels
                for _ in range(4):
                    yield cap_to_bits(unmasked, 4)
                    unmasked >>= 4

        self.pixels = [[0] * self.size.width for _ in range(self.size.height)]
        for i, pixel in enumerate(pixel_generator()):
            x, y = self.get_pos(i)
            self.pixels[y][x] = pixel
        print i, x, y

        return self

    def get_pos(self, idx, tile_size=None):
        """Given a linearized index, returns the x, y coordinates within the
        image.

        If `tile_size` is provided, the image is assumed to be constructed from
        square tiles of that size, and each tile is filled before the next is
        begin.
        """
        if tile_size:
            tile_no = idx // tile_size ** 2
            # coordinates of the tile; 0,0 is first tile, 0,1 is second, etc
            tile_x = tile_no % (self.size.width // tile_size)
            tile_y = tile_no // (self.size.width // tile_size)

            # idx within the tile
            tile_idx = idx % tile_size ** 2

            # Now we just need the x,y within the tile, plus the offsets for
            # the tile itself
            return (tile_x * tile_size + tile_idx %  tile_size,
                    tile_y * tile_size + tile_idx // tile_size)


        # Without tiles, this is rather simpler
        return idx % self.size.width, idx // self.size.width

    def fake_color(self, idx):
        """Given a palette index, returns a unique fake color to represent it.
        """
        sat = idx * 2
        return sat, sat, sat

    def png(self, palette=None):
        """Returns this sprite as a PNG.  Colors are merely shades of gray,
        unless a palette is provided."""
        writer_options = {'size': self.size}

        if palette:
            writer_options['palette'] = palette.colors
            writer_options['alpha'] = True
            writer_options['bitdepth'] = 5

            # First entry is transparent
            writer_options['palette'][0] += (0,)
        else:
            writer_options['greyscale'] = True
            writer_options['transparent'] = 0
            writer_options['bitdepth'] = 4

        writer = png.Writer(**writer_options)
        buffer = StringIO()

        writer.write(buffer, self.pixels)
        return buffer.getvalue()

    def __str__(self):
        """Returns this sprite as a PNG."""
        return self.png()
