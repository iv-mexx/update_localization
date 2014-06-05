#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
#   @author     Markus Chmelar
#   @date       2012-12-23
#   @version    1
# ------------------------------------------------------------------------------

'''
This script helps keeping the LocalizedStrings in an Xcode project up-to-date.

Rather than replacing all entries like genstrings does, this script keeps track of which entries are already translated and saves them. 

The code is inspired by the script update_strings written by the user ndfred on StackOverflow
(http://stackoverflow.com/users/303539/ndfred) and published in this post http://stackoverflow.com/questions/9895621/best-practice-using-nslocalizedstring
Some snippets are taken from his original script, but the most part was rewritten by me.

I have added support for
    - Multiple Translation Tables
    - Excluding Files and Paths that match an ignore-pattern
    - Added Option for specifying file-extensions that should be scanned
    - Added Support for Default-Values

Futhermoer, the Localized.strings files are now created with a formatting that is equal to the original formatting



Copyright (c) 2012 Markus Chmelar / Innovaptor OG

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

'''
# -- Import --------------------------------------------------------------------
# Regular Expressions
import re
# Operation Systems and Path Operations
import os
# System Utilities
import sys
# Creating and using Temporal File
import tempfile
# Running Commands on the Commandline
import subprocess
# Opening Files with different Encodings
import codecs
# Commandline Options parser
import optparse
# High Level File Operations
import shutil
# Logging
import logging
# Doc-Tests
import doctest

# -- Class ---------------------------------------------------------------------


class LocalizedStringLineParser(object):
    ''' Parses single lines and creates LocalizedString objects from them'''
    def __init__(self):
        # Possible Parsing states indicating what is waited for
        self.ParseStates = {'COMMENT': 1, 'STRING': 2, 'TRAILING_COMMENT': 3, 
                            'STRING_MULTILINE': 4, 'COMMENT_MULTILINE' :5}
        # The parsing state indicates what the last parsed thing was
        self.parse_state = self.ParseStates['COMMENT']
        self.key = None
        self.value = None
        self.comment = None

    def parse_line(self, line):
        ''' Parses a single line. Keeps track of the current state and creates
        LocalizedString objects as appropriate

        Keyword arguments:

            line
                The next line to be parsed

        Examples

            >>> parser = LocalizedStringLineParser()
            >>> string = parser.parse_line('    ')
            >>> string

            >>> string = parser.parse_line('/* Comment1 */')
            >>> string

            >>> string = parser.parse_line('    ')
            >>> string

            >>> string = parser.parse_line('"key1" = "value1";')
            >>> string.key
            'key1'
            >>> string.value
            'value1'
            >>> string.comment
            'Comment1'

            >>> string = parser.parse_line('/* Comment2 */')
            >>> string

            >>> string = parser.parse_line('"key2" = "value2";')
            >>> string.key
            'key2'
            >>> string.value
            'value2'
            >>> string.comment
            'Comment2'


            >>> parser = LocalizedStringLineParser()
            >>> string = parser.parse_line('"KEY3" = "VALUE3"; /* Comment3 */')
            >>> string.key
            'KEY3'
            >>> string.value
            'VALUE3'
            >>> string.comment
            'Comment3'



            >>> parser = LocalizedStringLineParser()
            >>> string = parser.parse_line('/* Comment4 */')
            >>> string

            >>> string = parser.parse_line('"KEY4" = "VALUE4')
            >>> string

            >>> string = parser.parse_line('VALUE4_LINE2";')
            >>> string.key
            'KEY4'
            >>> string.value
            'VALUE4\\nVALUE4_LINE2'

            >>> parser = LocalizedStringLineParser()
            >>> string = parser.parse_line('/* Line 1')
            
            >>> string = parser.parse_line(' Line 2')
            
            >>> string = parser.parse_line(' Line 3 */')
            
            >>> string = parser.parse_line('"key" = "value";')
            
            >>> string.key
            'key'
            >>> string.value
            'value'
            >>> string.comment
            'Line 1\\n Line 2\\n Line 3 '
        '''
        if self.parse_state == self.ParseStates['COMMENT']:
            (self.key, self.value, self.comment) = LocalizedString.parse_trailing_comment(line)
            if self.key is not None and self.value is not None and self.comment is not None:
                return self.build_localizedString()
            self.comment = LocalizedString.parse_comment(line)
            if self.comment is not None:
                self.parse_state = self.ParseStates['STRING']
                return None
            # Maybe its a multiline comment
            self.comment_partial = LocalizedString.parse_multiline_comment_start(line)
            if self.comment_partial is not None:
                self.parse_state = self.ParseStates['COMMENT_MULTILINE']
            return None

        elif self.parse_state == self.ParseStates['COMMENT_MULTILINE']:
            comment_end = LocalizedString.parse_multiline_comment_end(line)
            if comment_end is not None:
                self.comment = self.comment_partial + '\n' + comment_end
                self.comment_partial = None
                self.parse_state = self.ParseStates['STRING']
                return None
            # Or its just an intermediate line
            comment_line = LocalizedString.parse_multiline_comment_line(line)
            if comment_line is not None:
                self.comment_partial = self.comment_partial + '\n' + comment_line
            return None

        elif self.parse_state == self.ParseStates['TRAILING_COMMENT']:
            self.comment = LocalizedString.parse_comment(line)
            if self.comment is not None:
                self.parse_state = self.ParseStates['COMMENT']
                return self.build_localizedString()
            return None

        elif self.parse_state == self.ParseStates['STRING']:
            (self.key, self.value) = LocalizedString.parse_localized_pair(
                line
            )
            if self.key is not None and self.value is not None:
                self.parse_state = self.ParseStates['COMMENT']
                return self.build_localizedString()
            # Otherwise, try if the Value is multi-line
            (self.key, self.value_partial) = LocalizedString.parse_multiline_start(
                line
            )
            if self.key is not None and self.value_partial is not None:
                self.parse_state = self.ParseStates['STRING_MULTILINE']
                self.value = None
            return None
        elif self.parse_state == self.ParseStates['STRING_MULTILINE']:
            value_part = LocalizedString.parse_multiline_end(line)
            if value_part is not None:
                self.value = self.value_partial + '\n' + value_part
                self.value_partial = None
                self.parse_state = self.ParseStates['COMMENT']
                return self.build_localizedString()
            value_part = LocalizedString.parse_multiline_line(line)
            if value_part is not None:
                self.value_partial = self.value_partial + '\n' +  value_part
            return None


    def build_localizedString(self):
        localizedString = LocalizedString(
            self.key,
            self.value,
            self.comment
        )
        self.key = None
        self.value = None
        self.comment = None
        return localizedString

class LocalizedString(object):
    ''' A localizes string entry with key, value and comment'''
    COMMENT_EXPR = re.compile(
        # Line start
        '^\w*'
        # Comment
        '/\* (?P<comment>.+) \*/'
        # End of line
        '\w*$'
    )
    COMMENT_MULTILINE_START = re.compile(
        # Line start
        '^\w*'
        # Comment
        '/\* (?P<comment>.+)'
        # End of line
        '\w*$'
    )
    COMMENT_MULTILINE_LINE = re.compile(
        # Line start
        '^'
        # Value
        '(?P<comment>.+)'
        # End of line
        '$'
    )
    COMMENT_MULTILINE_END = re.compile(
        # Line start
        '^'
        # Comment
        '(?P<comment>.+)\*/'
        # End of line
        '\s*$'
    )
    LOCALIZED_STRING_EXPR = re.compile(
        # Line start
        '^'
        # Key
        '"(?P<key>.+)"'
        # Equals
        ' ?= ?'
        # Value
        '"(?P<value>.+)"'
        # Whitespace
        ';'
        # End of line
        '$'
    )
    LOCALIZED_STRING_MULTILINE_START_EXPR = re.compile(
        # Line start
        '^'
        # Key
        '"(?P<key>.+)"'
        # Equals
        ' ?= ?'
        # Value
        '"(?P<value>.+)'
        # End of line
        '$'
    )
    LOCALIZED_STRING_MULTILINE_LINE_EXPR = re.compile(
        # Line start
        '^'
        # Value
        '(?P<value>.+)'
        # End of line
        '$'
    )
    LOCALIZED_STRING_MULTILINE_END_EXPR = re.compile(
        # Line start
        '^'
        # Value
        '(?P<value>.+)"'
        # Whitespace
        ' ?; ?'
        # End of line
        '$'
    )
    LOCALIZED_STRING_TRAILING_COMMENT_EXPR = re.compile(
        # Line start
        '^'
        # Key
        '"(?P<key>.+)"'
        # Equals
        ' ?= ?'
        # Value
        '"(?P<value>.+)"'
        # Whitespace
        ' ?; ?'
        # Comment
        '/\* (?P<comment>.+) \*/'
        # End of line
        '$'

    )

    @classmethod
    def parse_multiline_start(cls, line):
        ''' Parse the beginning of a multi-line entry, "KEY"="VALUE_LINE1

        Keyword arguments:

            line
                The line to be parsed

        Returns
            ``tuple`` with key, value and comment
            ``None`` when the line was no comment

        Examples

            >>> line = '"key" = "value4'
            >>> LocalizedString.parse_multiline_start(line)
            ('key', 'value4')

        '''
        result = cls.LOCALIZED_STRING_MULTILINE_START_EXPR.match(line)
        if result is not None:
            return (result.group('key'),
                    result.group('value'))
        else:
            return (None, None)

    @classmethod
    def parse_multiline_line(cls, line):
        ''' Parse an intermediate line of a multi-line entry, only value

        Keyword arguments:

            line
                The line to be parsed

        Returns
            ``String`` with the value
            ``None`` when the line was no comment

        Examples

            >>> line = 'value4, maybe something else'
            >>> LocalizedString.parse_multiline_line(line)
            'value4, maybe something else'
        '''
        result = cls.LOCALIZED_STRING_MULTILINE_LINE_EXPR.match(line)
        if result is not None:
            return result.group('value')
        return None


    @classmethod
    def parse_multiline_end(cls, line):
        ''' Parse an end line of a multi-line entry, only value

        Keyword arguments:

            line
                The line to be parsed

        Returns
            ``String`` the value 
            ``None`` when the line was no comment

        Examples

            >>> line = 'value4, maybe something else";'
            >>> LocalizedString.parse_multiline_end(line)
            'value4, maybe something else'
        '''
        result = cls.LOCALIZED_STRING_MULTILINE_END_EXPR.match(line)
        if result is not None:
            return result.group('value')
        return None


    @classmethod
    def parse_trailing_comment(cls, line):
        '''Extract the content of a line with a trailing comment.

        Keyword arguments:

            line
                The line to be parsed

        Returns
            ``tuple`` with key, value and comment
            ``None`` when the line was no comment

        Examples

            >>> line = '"key3" = "value3";/* Bla */'
            >>> LocalizedString.parse_trailing_comment(line)
            ('key3', 'value3', 'Bla')
        '''
        result = cls.LOCALIZED_STRING_TRAILING_COMMENT_EXPR.match(line)
        if result is not None:
            return (
                result.group('key'),
                result.group('value'),
                result.group('comment')
            )
        else:
            return (None, None, None)

    @classmethod
    def parse_multiline_comment_start(cls, line):
        '''
        Example:

            >>> LocalizedString.parse_multiline_comment_start('/* Hello ')
            'Hello '
        '''
        result = cls.COMMENT_MULTILINE_START.match(line)
        if result is not None:
            return result.group('comment')
        else:
            return None


    @classmethod
    def parse_multiline_comment_line(cls, line):
        '''
        Example:

            >>> LocalizedString.parse_multiline_comment_line(' Line ')
            ' Line '
        '''
        result = cls.COMMENT_MULTILINE_LINE.match(line)
        if result is not None:
            return result.group('comment')
        else:
            return None


    @classmethod
    def parse_multiline_comment_end(cls, line):
        '''
        Example:

            >>> LocalizedString.parse_multiline_comment_end(' End */ ')
            ' End '
        '''
        result = cls.COMMENT_MULTILINE_END.match(line)
        if result is not None:
            return result.group('comment')
        else:
            return None

    @classmethod
    def parse_comment(cls, line):
        '''Extract the content of a comment line from a line.

        Keyword arguments:

            line
                The line to be parsed

        Returns
            ``string`` with the Comment or
            ``None`` when the line was no comment

        Examples

            >>> LocalizedString.parse_comment('This line is no comment')
            >>> LocalizedString.parse_comment('')
            >>> LocalizedString.parse_comment('/* Comment */')
            'Comment'
        '''
        result = cls.COMMENT_EXPR.match(line)
        if result is not None:
            return result.group('comment')
        else:
            return None

    @classmethod
    def parse_localized_pair(cls, line):
        '''Extract the content of a key/value pair from a line.

        Keyword arguments:

            line
                The line to be parsed

        Returns
            ``tupple`` with key and value as strings
            ``tupple`` (None, None) when the line was no match

        Examples

            >>> LocalizedString.parse_localized_pair('Some Line')
            (None, None)
            >>> LocalizedString.parse_localized_pair('/* Comment */')
            (None, None)
            >>> LocalizedString.parse_localized_pair('"key1" = "value1";')
            ('key1', 'value1')
        '''
        result = cls.LOCALIZED_STRING_EXPR.match(line)
        if result is not None:
            return (
                result.group('key'),
                result.group('value')
            )
        else:
            return (None, None)

    def __eq__(self, other):
        '''Tests Equality of two LocalizedStrings

        >>> s1 = LocalizedString('key1', 'value1', 'comment1')
        >>> s2 = LocalizedString('key1', 'value1', 'comment1')
        >>> s3 = LocalizedString('key1', 'value2', 'comment1')
        >>> s4 = LocalizedString('key1', 'value1', 'comment2')
        >>> s5 = LocalizedString('key1', 'value2', 'comment2')
        >>> s1 == s2
        True
        >>> s1 == s3
        False
        >>> s1 == s4
        False
        >>> s1 == s5
        False
        '''
        if isinstance(other, LocalizedString):
            return (self.key == other.key and self.value == other.value and
                    self.comment == other.comment)
        else:
            return NotImplemented

    def __neq__(self, other):
        result = self.__eq__(other)
        if(result is NotImplemented):
            return result
        return not result

    def __init__(self, key, value=None, comment=None):
        super(LocalizedString, self).__init__()
        self.key = key
        self.value = value
        self.comment = comment

    def is_raw(self):
        '''
        Return True if the localized string has not been translated.

        Examples
            >>> l1 = LocalizedString('key1', 'valye1', 'comment1')
            >>> l1.is_raw()
            False
            >>> l2 = LocalizedString('key2', 'key2', 'comment2')
            >>> l2.is_raw()
            True
        '''
        return self.value == self.key

    def __str__(self):
        if self.comment:
            return '/* %s */\n"%s" = "%s";\n' % (
                self.comment, self.key or '', self.value or '',
            )
        else:
            return '"%s" = "%s";\n' % (self.key or '', self.value or '')

# -- Methods -------------------------------------------------------------------

ENCODINGS = ['utf16', 'utf8']


def merge_strings(old_strings, new_strings, keep_comment=False):
    '''Merges two dictionarys, one with the old strings and one with the new
    strings.
    Old strings keep their value but their comment will be updated. Only if
    the string is 'raw' which means its value is equal to its key, the value
    will be replaced by the new one.
    But because the method has to work with NSLocalizedStringWithDefaultValue
    as well it is not possible to detect untranslated strings with default value
    so if the default value changes this will not be updated!

    Keyword arguments:

        old_strings
            Dictionary with the Strings that were already there

        new_strings
            Dictionary with the new Strings

        keep_comment
            If True, the old comment will be kept. This is necessary for
            translating Storyboard files because they have generated comments
            which are not very helpfull

    Returns

        Merged Dictionary

    Examples:

        >>> old_dict = {}
        >>> old_dict['key1'] = LocalizedString('key1', 'value1', 'comment1')
        >>> old_dict['key2'] = LocalizedString('key2', 'value2', 'comment2')
        >>> old_dict['key3'] = LocalizedString('key3', 'key3', 'comment3')
        >>> new_dict = {}
        >>> new_dict['key1'] = LocalizedString('key1', 'key1', 'comment1')
        >>> new_dict['key2'] = LocalizedString('key2', 'key2', 'comment2_new')
        >>> new_dict['key4'] = LocalizedString('key4', 'key4', 'comment4')
        >>> new_dict['key3'] = LocalizedString('key3', 'value3', 'comment3')
        >>> merge_dict = merge_strings(old_dict, new_dict)
        >>> merge_dict['key1'].value
        'value1'
        >>> merge_dict['key1'].comment
        'comment1'
        >>> merge_dict['key2'].value
        'value2'
        >>> merge_dict['key2'].comment
        'comment2_new'
        >>> merge_dict['key3'].value
        'value3'
        >>> merge_dict['key3'].comment
        'comment3'
        >>> merge_dict['key4'].value
        'key4'
        >>> merge_dict['key4'].comment
        'comment4'

        >>> old_dict_2 = {}
        >>> new_dict_2 = {}
        >>> old_dict_2['key1'] = LocalizedString('key1', 'value1', 'comment1')
        >>> new_dict_2['key1'] = LocalizedString('key1', 'value1', 'comment2')
        >>> merged_1 = merge_strings(old_dict_2, new_dict_2, keep_comment=False)
        >>> merged_1['key1'].value
        'value1'
        >>> merged_1['key1'].comment
        'comment2'
        >>> old_dict_2['key1'] = LocalizedString('key1', 'value1', 'comment1')
        >>> new_dict_2['key1'] = LocalizedString('key1', 'value1', 'comment2')
        >>> merged_2 = merge_strings(old_dict_2, new_dict_2, keep_comment=True)
        >>> merged_2['key1'].value
        'value1'
        >>> merged_2['key1'].comment
        'comment1'
    '''
    merged_strings = {}
    for key, old_string in old_strings.iteritems():
        if key in new_strings:
            new_string = new_strings[key]
            if old_string.is_raw():
                # if the old string is raw just take the new string
                if keep_comment:
                    new_string.comment = old_string.comment
                merged_strings[key] = new_string
            else:
                # otherwise take the value of the old string but the comment of the new string
                new_string.value = old_string.value
                if keep_comment:
                    new_string.comment = old_string.comment
                merged_strings[key] = new_string
            # remove the string from the new strings
            del new_strings[key]
        else:
            # If the String is not in the new Strings anymore it has been removed
            # TODO: Include option to not remove old keys!
            pass
    # All strings that are still in the new_strings dict are really new and can be copied
    for key, new_string in new_strings.iteritems():
        merged_strings[key] = new_string

    return merged_strings


def parse_file(file_path, encoding='utf16'):
    ''' Parses a file and creates a dictionary containing all LocalizedStrings
        elements in the file

        Keyword arguments:

            file_path
                path to the file that should be parsed

            encoding
                encoding of the file

        Returns:    ``dict``
    '''
    
    with codecs.open(file_path, mode='r', encoding=encoding) as file_contents:
        logging.debug("Parsing File: {}".format(file_path))
        parser = LocalizedStringLineParser()
        localized_strings = {}
        try:
            for line in file_contents:
                localized_string = parser.parse_line(line)
                if localized_string is not None:
                    localized_strings[localized_string.key] = localized_string
        except UnicodeError:
            logging.debug("Failed to open file as UTF16, Trying UTF8")
            file_contents = codecs.open(file_path, mode='r', encoding='utf8')
            for line in file_contents:
                localized_string = parser.parse_line(line)
                if localized_string is not None:
                    localized_strings[localized_string.key] = localized_string
    return localized_strings


def write_file(file_path, strings, encoding='utf16'):
    '''Writes the strings to the given file
    '''
    with codecs.open(file_path, 'w', encoding) as output:
        for string in sort_strings(strings):
            output.write('%s\n' % string)


def strings_to_file(localized_strings, file_path, encoding='utf16'):
    '''
    Write a strings file at file_path containing string in
    the localized_strings dictionnary.
    The strings are alphabetically sorted.
    '''
    with codecs.open(file_path, 'w', encoding) as output:
        for localized_string in sorted_strings_from_dict(localized_strings):
            output.write('%s\n' % localized_string)


def sort_strings(strings):
    '''Returns an array that contains all LocalizedStrings objects of the
    dictionary, sorted alphabetically
    '''
    keys = strings.keys()
    keys.sort()

    values = []
    for key in keys:
        values.append(strings[key])

    return values


def find_sources(folder_path, extensions=None, ignore_patterns=None):
    '''Finds all source-files in the path that fit the extensions and
    ignore-patterns

    Keyword arguments:

        folder_path
            The path to the folder, all files in this folder will recursively
            be searched

        extensions
            If this parameter is different to None, only files with the given
            extension will be used
            If None, defaults to [c, m, mm]

        ignore_patterns
            If this parameter is different to None, files which path match the
            ignore pattern will be ignored

    Returns:

        Array with paths to all files that have to be used with genstrings

    Examples:

        >>> find_sources('TestInput')
        ['TestInput/test.m', 'TestInput/3rdParty/test2.m']

        >>> find_sources('TestInput', ['h', 'm'])
        ['TestInput/test.h', 'TestInput/test.m', 'TestInput/3rdParty/test2.h', 'TestInput/3rdParty/test2.m']

        >>> find_sources('TestInput', ['h', 'm'], ['3rdParty'])
        ['TestInput/test.h', 'TestInput/test.m']

        >>> find_sources('TestInput', ignore_patterns=['3rdParty'])
        ['TestInput/test.m']
    '''
    # First run genstrings on all source-files
    code_file_paths = []
    if extensions is None:
        extensions = frozenset(['c', 'm', 'mm'])

    for dir_path, dir_names, file_names in os.walk(folder_path):
        ignorePath = False
        if ignore_patterns is not None:
            for ignore_pattern in ignore_patterns:
                if ignore_pattern in dir_path:
                    logging.debug('IGNORED Path: {}'.format(dir_path))
                    ignorePath = True
        if ignorePath is False:
            logging.debug('DirPath: {}'.format(dir_path))
            for file_name in file_names:
                extension = file_name.rpartition('.')[2]
                if extension in extensions:
                    code_file_path = os.path.join(dir_path, file_name)
                    code_file_paths.append(code_file_path)
    logging.info('Found %d files', len(code_file_paths))
    return code_file_paths


def gen_strings_interface(folder_path, gen_path=None, ignore_patterns=None):
    '''Generates strings for all interface files in the path
    '''
    extensions = ['xib', 'nib', 'storyboard']
    code_file_paths = find_sources(folder_path, extensions, ignore_patterns)

    if gen_path is None:
        gen_path = code_file_paths

    logging.debug('Running ibtool')
    temp_folder_path = tempfile.mkdtemp()

    for code_file_path in code_file_paths:
        (file_path, file_name) = os.path.split(code_file_path)
        target_path = os.path.splitext(file_name)[0] + '.strings'
        file_name = os.path.basename(code_file_path)
        file_name = os.path.splitext(file_name)[0] + '.strings'
        export_path = os.path.join(temp_folder_path, file_name)
        arguments = ['ibtool', '--export-strings-file', export_path,
                     code_file_path]
        logging.debug('Arguments: {}'.format(arguments))
        subprocess.call(arguments)
        # For each file (which is a single Table) read the corresponding existing file and combine them
        logging.debug('Temp File found: {}'.format(export_path))
        current_file_path = os.path.join(gen_path, target_path)
        merge_files(export_path, current_file_path, gen_path, keep_comment=True)
        os.remove(export_path)
    shutil.rmtree(temp_folder_path)


def gen_strings(folder_path, gen_path=None, extensions=None, ignore_patterns=None):
    '''Runs gen-strings on all files in the path.

    Keyword arguments:

        folder_path
            The path to the folder, all files in this folder will recursively
            be searched

        gen_path
            The path to the folder where the LocalizedString Files should be
            created

        extensions
            If this parameter is different to None, only files with the given
            extension will be used
            If None, defaults to [c, m, mm]

        ignore_patterns
            If this parameter is different to None, files which path match the
            ignore pattern will be ignored
    '''
    code_file_paths = find_sources(folder_path, extensions, ignore_patterns)

    if gen_path is None:
        gen_path = code_file_paths

    logging.debug('Running genstrings')
    temp_folder_path = tempfile.mkdtemp()

    arguments = ['genstrings', '-u', '-o', temp_folder_path]
    arguments.extend(code_file_paths)
    subprocess.call(arguments)
    logging.debug('Temp Path: {}'.format(temp_folder_path))

    #Read the Strings from the new generated strings
    for temp_file in os.listdir(temp_folder_path):
        # For each file (which is a single Table) read the corresponding existing file and combine them
        logging.debug('Temp File found: {}'.format(temp_file))
        temp_file_path = os.path.join(temp_folder_path, temp_file)
        current_file_path = os.path.join(gen_path, temp_file)
        merge_files(temp_file_path, current_file_path, gen_path)
        os.remove(temp_file_path)
    shutil.rmtree(temp_folder_path)


def merge_files(new_file_path, old_file_path, folder_path, keep_comment=False):
    '''Scans the Strings in both files, merges them together and writes the
    result to the old file

    Keyword Arguments

        new_file_path
            Path to the new generated strings file

        old_file_path
            Path to the existing strings file
    '''
    new_strings = parse_file(new_file_path)
    logging.debug('Current File: {}'.format(old_file_path))
    if os.path.exists(old_file_path):
        logging.debug('File Exists, merge them')
        old_strings = parse_file(old_file_path)
        final_strings = merge_strings(old_strings, new_strings, keep_comment)
        write_file(old_file_path, final_strings)
    else:
        logging.info('File {} is new'.format(new_file_path))
        shutil.copy(new_file_path, folder_path)


def main():
    ''' Parse the command line and execute the programm with the parameters '''

    parser = optparse.OptionParser(
        'usage: %prog [options] [output folder] [source folders] [ignore patterns]'
    )
    parser.add_option(
        '-i',
        '--input',
        action='store',
        dest='input_path',
        default='.',
        help='Input Path where the Source-Files are'
    )
    parser.add_option(
        '-o',
        '--output',
        action='store',
        dest='output_path',
        default='.',
        help='Output Path where the .strings File should be generated'
    )
    parser.add_option(
        '-v',
        '--verbose',
        action='store_true',
        dest='verbose',
        default=False,
        help='Show debug messages'
    )
    parser.add_option(
        '',
        '--unittests',
        action='store_true',
        dest='unittests',
        default=False,
        help='Run unit tests (debug)'
    )
    parser.add_option(
        '--ignore',
        action='append',
        dest='ignore_patterns',
        default=None,
        help='Ignore Paths that match the patterns'
    )
    parser.add_option(
        '--extension',
        action='append',
        dest='extensions',
        default=None,
        help='File-Extensions that should be scanned'
    )
    parser.add_option(
        '--interface',
        action='store_true',
        dest='interface',
        default=False,
        help='Also Localize Interface files'
    )

    (options, args) = parser.parse_args()

    # Create Logger
    logging.basicConfig(
        format='%(message)s',
        level=options.verbose and logging.DEBUG or logging.INFO
    )

    # Run Unittests/Doctests
    if options.unittests:
        doctest.testmod()
        return

    gen_strings(folder_path=options.input_path,
                gen_path=options.output_path,
                extensions=options.extensions,
                ignore_patterns=options.ignore_patterns)

    if options.interface:
        gen_strings_interface(folder_path=options.input_path,
                              gen_path=options.output_path,
                              ignore_patterns=options.ignore_patterns)
    return 0

if __name__ == '__main__':
    sys.exit(main())
