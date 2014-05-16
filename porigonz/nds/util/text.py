# encoding: utf8
"""Utility functions and classes for working with DS text."""

from construct import *

from porigonz.nds.util import cap_to_bits

pokemon_encrypted_text_struct = Struct('pokemon_text',
    ULInt16('count'),
    ULInt16('key'),
    MetaRepeater(
        lambda ctx: ctx['count'],
        Struct('header',
            ULInt32('offset'),
            ULInt32('length'),
        ),
    ),
)

class CharacterTable(object):
    friendly_display_mapping = {
        ord(u'\r'): u'\\r',
        ord(u'\n'): u'\\n',
        ord(u'\f'): u'\\f',
        ord(u'\t'): u'\\t',
    }

    def __init__(self):
        self.mapping_table = {}
        pass

    @classmethod
    def from_stream(cls, f):
        self = cls()
        for line in f:
            line = line.decode('utf8')

            from_, _, to = line.partition(u'=')
            from_ = int(from_, 16)

            # Character table contains some escapes
            to = to.rstrip(u'\n')
            if to == u'\\n':
                to = u'\n'
            elif to == u'\\r':
                to = u'\r'
            elif to == u'\\f':
                to = u'\f'
            elif to.startswith(u'\\x'):
                # XXX are these correct or necessary?  they tend to map abcd to \xabcd
                to = unichr(int(to[2:6], 16))

            self.add_mapping(from_, to)

        return self

    def add_mapping(self, from_, to):
        """Adds a character mapping.

        `from_` may be either an integer or a character.
        `to` must be a unicode character.
        """
        if isinstance(from_, basestring):
            from_ = ord(from_)

        self.mapping_table[from_] = to


    def escape_control_chars(self, string):
        """Returns `string` with control characters escaped.

        C-style single-letter escapes are used when possible.
        """
        return string.translate(self.friendly_display_mapping)

    def pokemon_decode_string(self, string):
        u"""Decodes (in the character set sense) a string of Pokémon text,
        returning real Unicode.
        """
        return string.translate(self.mapping_table)

    def pokemon_translate(self, src):
        u"""Translates a raw block of text to readable unicode, using the
        encryption from the Gen IV Pokémon games.

        These blocks actually contain a list of multiple strings.  The whole
        list is returned.
        """
        pokemon_junk = pokemon_encrypted_text_struct.parse(src)

        # <3 LoadingNOW for the original source

        # Decrypt the header
        # It's encrypted with some XOR shenanigans and 16-bit math.
        key = cap_to_bits(pokemon_junk.key * 0x02fd, 16)
        for i in range(pokemon_junk.count):
            curkey = cap_to_bits(key * (i + 1), 16)
            curkey = curkey | (curkey << 16)

            pokemon_junk.header[i].offset ^= curkey
            pokemon_junk.header[i].length ^= curkey

        # Translate this garbage, decrypting with this rotating key
        strings = []
        for i, header in enumerate(pokemon_junk.header):
            dest_chars = []

            offset = header.offset
            length = header.length

            key = ((i + 1) * 0x91bd3) & 0xffff
            for pos in xrange(length):
                # Characters are two bytes; get them and fix endianness
                n = (ord(src[offset + pos * 2 + 1]) << 8) \
                   | ord(src[offset + pos * 2])
                n ^= key

                dest_chars.append(unichr(n))

                # Rotate key
                key = (key + 0x493d) & 0xffff

            dest_string = u''.join(dest_chars)
            strings.append(self.escape_control_chars(self.pokemon_decode_string(dest_string)))

        return strings
