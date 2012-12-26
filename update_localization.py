#!/usr/bin/env python
# -*- coding: utf-8 -*-

# ------------------------------------------------------------------------------
#   @author     Markus Chmelar
#   @date       2012-12-23
#   @version    1
# ------------------------------------------------------------------------------

'''
This script helps keeping the LocalizedStrings in an Xcode Project up-to-date.

Rather than replacing all Entrys like genstrings does, this script keeps track of which entrys are already translated and saves them. 

The code is inspired by the script update_strings written by the user ndfred on StackOverflow
(http://stackoverflow.com/users/303539/ndfred) and published in this post http://stackoverflow.com/questions/9895621/best-practice-using-nslocalizedstring
Some snippets are taken from his original script but the most part was rewritten by me

I have added support for
    - Multiple Translation Tables
    - Excluding Files and Paths that match an ignore-pattern
    - Added Support for Default-Values

'''
# -- Import --------------------------------------------------------------------
# Regular Expressions
import re
# System Specific parameters and functions
import sys
# Operation Systems and Path Operations
import os
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
        self.ParseStates = {'COMMENT':1, 'STRING':2}    
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
        '''
        if self.parse_state == self.ParseStates['COMMENT']:
            self.comment = LocalizedString.parse_comment(line)
            if self.comment != None:
                self.parse_state = self.ParseStates['STRING']
            return None
        elif self.parse_state == self.ParseStates['STRING']:
            (self.key, self.value) = LocalizedString.parse_localized_pair(
                line
                )
            if self.key != None and self.value != None:
                self.parse_state = self.ParseStates['COMMENT']
                localizedString = LocalizedString(
                    self.key, 
                    self.value, 
                    self.comment
                    )
                self.key = None
                self.value = None
                self.comment = None
                return  localizedString
            return None
    
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
        if result != None:
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
        if result != None:
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
            
    def __neq__(slef, other):
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
            return ' /* %s */\n"%s" = "%s";\n' % (
                self.comment, self.key or '', self.value or '', 
            )
        else:
            return '"%s" = "%s";\n' % (self.key or '', self.value or '')

# -- Methods -------------------------------------------------------------------

ENCODINGS = ['utf16', 'utf8']

def merge_strings(old_strings, new_strings):
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
    '''
    merged_strings = {}
    for key, old_string in old_strings.iteritems():
        if new_strings.has_key(key):
            new_string = new_strings[key]
            if old_string.is_raw():
                # if the old string is raw just take the new string
                merged_strings[key] = new_string
            else:
                # otherwise take the value of the old string but the comment of the new string
                new_string.value = old_string.value
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
        
        Examples:
        
            >>> s = parse_file('TestFiles/Localizable.strings',\
                 encoding='utf16')
    '''
    
    with codecs.open(file_path, mode='r', encoding=encoding) as file_contents:
        logging.debug("Parsing File: {}".format(file_path))
        parser = LocalizedStringLineParser()
        localized_strings = {}
        for line in file_contents:
            localized_string = parser.parse_line(line)
            if localized_string != None:
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
    keys = strings.keys();
    keys.sort
    
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
    if extensions == None:
        extensions = frozenset(['c', 'm', 'mm'])

    for dir_path, dir_names, file_names in os.walk(folder_path):
        ignorePath = False
        if ignore_patterns != None:
            for ignore_pattern in ignore_patterns:
                if ignore_pattern in dir_path:
                    logging.debug('IGNORED Path: {}'.format(dir_path))
                    ignorePath = True
        if ignorePath == False:
            logging.debug('DirPath: {}'.format(dir_path))
            for file_name in file_names:
                extension = file_name.rpartition('.')[2]
                if extension in extensions:
                    code_file_path = os.path.join(dir_path, file_name)
                    code_file_paths.append(code_file_path)
    logging.info('Found %d files', len(code_file_paths))
    return code_file_paths

def gen_strings(folder_path, gen_path = None, extensions=None, ignore_patterns=None):
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
    
    Examples:
    
        >>> gen_strings('TestInput', 'TestFiles', ['m', 'h'], ['3rdParty'])
    '''
    code_file_paths = find_sources(folder_path, extensions, ignore_patterns)

    if gen_path == None:
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
        logging.debug('Analysing genstrings content')
        new_strings = parse_file(temp_file_path)
        current_file_path = os.path.join(gen_path, temp_file)
        logging.debug('Current File: {}'.format(current_file_path))
        if os.path.exists(current_file_path):
            logging.debug('File Exists, merge them')
            old_strings = parse_file(current_file_path)
            final_strings = merge_strings(old_strings, new_strings)
            write_file(current_file_path, final_strings)
        else:
            logging.info('File {} is new'.format(temp_file))
            shutil.copy(temp_file_path, folder_path)
        os.remove(temp_file_path)
    logging.debug('done')

    shutil.rmtree(temp_folder_path)
            
def main():
    ''' Parse the command line and do what it is telled to do '''
    
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
        default = None,
        help='Ignore Paths that match the patterns'
    )
    parser.add_option(
        '--extension',
        action='append',
        dest='extensions',
        default = None,
        help='File-Extensions that should be scanned'
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
        
    return 0
            
if __name__ == '__main__':
    doctest.testmod()
    sys.exit(main())