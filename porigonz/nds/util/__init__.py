# encoding: utf8
"""Miscellaneous helpers for dealing with DS data."""

def cap_to_bits(n, bits=32):
    return n & ((1 << bits) - 1)

def word_iterator(source, word_size):
    """Interprets source as a sequence of little-endian words, word_size bits
    each.
    """

    mask = (1 << word_size) - 1

    current_word = 0
    current_len = 0
    for ch in source:
        # Add in some bits
        current_word = (ord(ch) << current_len) | current_word
        current_len += 8

        # If there are enough bits for a word, split them off and yield
        while current_len >= word_size:
            new_word = current_word & mask

            current_word >>= word_size
            current_len -= word_size

            yield new_word
