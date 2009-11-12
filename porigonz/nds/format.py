# encoding: utf8
"""Converting DS files to some sort of computer/human-readable form.

Every function in this module has one required argument: `chunks`, a list of
chunks to format.  It may be a single file; it may be a list of files pulled
from a NARC; it may be a single file pulled from a NARC; it may be an
assortment of several DS files.  Or you may have created it yourself.  It's all
good.

Other arguments are cheerfully ignored.

Functions may return either an iterator or a list.  If you absolutely need a
list, always use `list()` on the return value.
"""

import binascii
import pkg_resources

from porigonz.nds.util.sprites import Sprite, Palette
from porigonz.nds.util.text import CharacterTable
from porigonz.nds.util.texture import NSBTX


def raw(chunks, *args, **kwargs):
    """Returns the original chunks unchanged."""
    return chunks

def hex(chunks, *args, **kwargs):
    """Returns the chunks as strings of hexadecimal digits, two to a byte."""
    return (binascii.hexlify(chunk) for chunk in chunks)

def sprite(chunks, *args, **kwargs):
    """Returns the sprites converted into conve"""

def sprite_part(chunks, *args, **kwargs):
    """Decrypt the chunks, detecting them as either palettes or regular sprites.
    """

    def generator(chunks):
        for chunk in chunks:
            if len(chunk) < 4:
                yield None
            elif chunk[0:4] == 'RLCN':
                yield Palette(chunk)
            elif chunk[0:4] == 'RGCN':
                try:
                    yield Sprite.from_standard(chunk)
                except:
                    yield None
            else:
                yield None

    return generator(chunks)



def texture(chunks, *args, **kwargs):
    """textures"""
    for tex in texture_part(chunks):
        for palette in tex.palettes:
            for texture in tex.textures:
                yield texture.png(palette)

def texture_part(chunks):
    for chunk in chunks:
        if chunk[:4] == 'BTX0':
            btx = NSBTX(chunk)
            # i've never seen a btx0 chunk with more than one block,
            # but that's not going to stop me!
            for tex in btx.blocks:
                yield tex
        elif chunk[:4] == 'BMD0':
            # this might have a texture we can use, but
            # i don't know how to deal with them yet
            pass
        else:
            pass

def overworld_sprites(chunks, *args, **kwargs):
    for tex in texture_part(chunks):
        yield tex



### Pokémon-specific

def pokemon_text(chunks, *args, **kwargs):
    """Decrypts the chunks with Pokémon text encryption.

    As each chunk contains multiple blocks of text, each returned element
    itself consists of multiple lines, with a newline after each.  This sucks
    and may change in the future, but to my knowledge the Pokémon games do not
    include any literal newlines in their text blocks; they are all "\\n".
    """
    # LoadingNOW is awesome.
    stream = pkg_resources.resource_stream('porigonz', 'data/pokemon.tbl')
    tbl = CharacterTable.from_stream(stream)

    return ("\n".join( tbl.pokemon_translate(chunk) ) for chunk in chunks)

def pokemon_sprite(chunks, *args, **kwargs):
    """Decrypt the chunks with Pokémon sprite encryption.

    For every sequence of (sprite, sprite, ..., palette, palette, ...), this
    will return all the palettes applied to all the sprites.  This will only
    work for the main Pokémon and perhaps the trainers—NOT the other_poke
    file.

    Returns a list of PNG data.
    """

    def generator(chunks):
        sprs = []
        pals = []
        for part in pokemon_sprite_part(chunks):
            if part == None:
                continue

            if isinstance(part, Sprite) and not pals:
                # If it's a sprite and we haven't seen any palettes, just stash it
                sprs.append(part)

            elif isinstance(part, Palette):
                # If it's a palette, always stash it
                pals.append(part)

            else:
                # Otherwise, we have a sprite, and there are already palettes.
                # This means we have a complete set
                for sprite in sprs:
                    for palette in pals:
                        yield sprite.png(palette=palette)

                # Then reset both lists and continue as normal
                sprs = [part]
                pals = []

        # If there's anything left, that's also a complete set
        if sprs and pals:
            for sprite in sprs:
                for palette in pals:
                    yield sprite.png(palette=palette)

    return generator(chunks)


def pokemon_sprite_part(chunks, *args, **kwargs):
    """Decrypt the chunks, detecting them as either palettes or Pokémon sprites.

    Return value is a list of Sprite and Palette objects corresponding to the
    original chunks.  Unrecognized chunks become None.
    """

    def generator(chunks):
        for chunk in chunks:
            if len(chunk) < 4:
                yield None
            elif chunk[0:4] == 'RLCN':
                yield Palette(chunk)
            elif chunk[0:4] == 'RGCN':
                yield Sprite.from_pokemon(chunk)
            else:
                yield None

    return generator(chunks)

def pokemon_overworld_sprites(chunks, shiny=False, *args, **kwargs):
    for tex in texture_part(chunks):
        if getattr(tex, 'name', None) != 'tsure_poke':
            continue
            
        palette = tex.palettes[1 if shiny else 0]
        yield tex.png(palette)

def pokemon_overworld_sprites_shiny(chunks, *args, **kwargs):
    return pokemon_overworld_sprites(chunks, shiny=True, *args, **kwargs)

