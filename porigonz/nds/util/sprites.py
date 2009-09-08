# encoding: utf8
"""Handling NDS sprites."""

"""
(01:50:06 AM) Zhen Lin: well, if you want to do it again, I have the seed values for the encryption used in Platinum
(01:51:02 AM) Eevee: I don't think I ever implemented the real formula, since you beat me to finishing it
(01:51:11 AM) Zhen Lin: Ah
(01:51:16 AM) Zhen Lin: well, it's fairly simple
(01:51:47 AM) Zhen Lin: pika found out a few weeks/months later what it really was
(01:52:09 AM) Zhen Lin: the seed value for each file is the final 16-bit integer (call it q[3199])
(01:52:49 AM) Zhen Lin: We construct a mask m[i], i = 0 to 3199
(01:52:54 AM) Zhen Lin: m[3199] = q[3199]
(01:53:05 AM) Zhen Lin: m[i - 1] = m[i] * r + k
(01:53:11 AM) Zhen Lin: for particular constants r and k
(01:53:28 AM) Eevee: and then, what, xor it all?
(01:53:35 AM) Zhen Lin: yeah
(01:53:47 AM) Zhen Lin: decrypted value = q[i] XOR m[i]
(01:53:56 AM) Eevee: wow.  that is embarrassingly simple
(01:54:09 AM) Eevee: are r/k just arbitrary game-global constants?
(01:54:12 AM) Zhen Lin: yeah
(01:54:20 AM) Zhen Lin: same constants for trainer images, if I remember
(01:54:46 AM) Zhen Lin: For DP, r = 0x4E6D, k = 0x6073
(01:54:58 AM) Zhen Lin: for Platinum, r = 0xEB65, k = 0x61A1
(01:55:09 AM) Eevee: wonder why they changed them
(01:55:14 AM) Eevee: maybe they're based on something else
(01:55:19 AM) Zhen Lin: Maybe
(01:55:31 AM) Zhen Lin: Or maybe they wanted to annoy us for a few hours while we tried to find it
(01:55:50 AM) Eevee: haha they could have done much better if the goal was to personally irritate a handful of people
(01:55:56 AM) Zhen Lin: indeed
(02:06:24 AM) Zhen Lin: The algorithm is actually a simple pseudorandom number generator, and there are certain requirements for the choice of constants to be good. If you're interested: http://en.wikipedia.org/wiki/Linear_congruential_generator
"""

from collections import namedtuple
from cStringIO import StringIO

from construct import *
from PIL import Image

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
            r = ((palette_word & 0x001f)      ) * 255 // 31
            g = ((palette_word & 0x03e0) >> 5 ) * 255 // 31
            b = ((palette_word & 0x7c00) >> 10) * 255 // 31

            self.colors.append((r, g, b))

    def png(self):
        """Returns a PNG illustrating the colors in this palette."""

        img = Image.new(mode='RGB', size=(len(self.colors), 1), color=None)

        for i, color in enumerate(self.colors):
            img.putpixel((i, 0), color)

        img = img.resize((8 * len(self.colors), 8))

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()


# Nintendo character graphic resource
rgcn_struct = Struct('rgcn',
    Const(Bytes('magic', 4), 'RGCN'),
    Const(Bytes('bom', 4), '\xff\xfe\x00\x01'),
    ULInt32('length'),
    Const(ULInt16('header_length'), 0x10),
    ULInt16('num_sections'),
    MetaField('data', lambda ctx: ctx['length'] - ctx['header_length']),
)

# "Character" data
# Most of this seems totally wrong for Pokémon
rahc_struct = Struct('rahc',
    Const(Bytes('magic', 4), 'RAHC'),
    Const(ULInt8('header_length'), 0x20),
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
    MetaField('data', lambda ctx: 6400),  # XXX length is off by a factor of 1024??
)

# Thanks, Wikipedia!  Now I don't have to write these!
# These compute the modular multiplicative inverse of a mod m, which is used to
# construct the decryption mask for a Pokémon sprite.  They can also,
# hopefully, be used to break the cipher's constants in the first place.
def extended_gcd(a, b):
    x, last_x = 0, 1
    y, last_y = 1, 0
 
    while b:
        quotient = a // b
        a, b = b, a % b
        x, last_x = last_x - quotient*x, x
        y, last_y = last_y - quotient*y, y
 
    return (last_x, last_y, a)
 
 
def inverse_mod(a, m):
    x, q, gcd = extended_gcd(a, m)
 
    if gcd == 1:
        # x is the inverse, but we want to be sure a positive number is returned.
        return (x + m) % m
    else:
        # if gcd != 1 then a and m are not coprime and the inverse does not exist.
        return None

Size = namedtuple('Size', ['width', 'height'])

class Sprite(object):
    """Represents a DS sprite."""

    @classmethod
    def from_pokemon(cls, chunk):
        """Parses a Pokémon sprite from a chunk.

        This encryption is only used for the Pokémon themselves and trainers.
        Items, berries, the map, the bag, etc. are all regular DS sprites.
        """

        self = cls()

        rgcn = rgcn_struct.parse(chunk)
        rahc = rahc_struct.parse(rgcn.data)

        # XXX make these less constant sometime
        self.size = Size(width=160, height=80)
        #add = 0x89c3  # appears to be the first dummy block only
        add = 0x61a1
        mult = 0xeb65
        # D/P
        #add = 0xedf9
        #mult = 0x4e6d

        # Construct the decryption mask.  It starts with the last uint16 in the
        # data and is modified going backwards.
        # XXX use a generator for this
        # XXX surely there's some way to make this forwards
        mask = [0] * 3200
        # cheap way to get the last word (ha ha)
        mask[-1] = next(word_iterator(rahc.data[-2:], 16))
        for i in reversed(range(len(mask) - 1)):
            mask[i] = cap_to_bits(mask[i + 1] * mult + add, 16)

        # Unmask the sprite data
        self.pixels = [[0] * self.size.height for _ in range(self.size.width)]
        for i, word in enumerate(word_iterator(rahc.data, 16)):
            unmasked = word ^ mask[i]

            # This is 16 bits, and there are four bits per pixel, so we have
            # four pixels
            x, y = self.get_pos(i * 4)
            for _ in range(4):
                self.pixels[x][y] = unmasked & 0x0f
                unmasked >>= 4
                x += 1

        return self

    def get_pos(self, idx):
        """Given a linearized index, returns the x, y coordinates within the
        image.
        """
        return idx % self.size.width, idx // self.size.width

    def fake_color(self, idx):
        """Given a palette index, returns a unique fake color to represent it.
        """
        sat = idx * 255 / 15
        return sat, sat, sat

    def png(self):
        """Returns this sprite as a PNG.  Colors are merely shades of gray."""
        img = Image.new(mode='RGB', size=self.size, color=None)

        for x in xrange(self.size.width):
            for y in xrange(self.size.height):
                img.putpixel((x, y), self.fake_color(self.pixels[x][y]))

        buffer = StringIO()
        img.save(buffer, 'PNG')
        return buffer.getvalue()
