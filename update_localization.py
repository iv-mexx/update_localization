# coding=utf-8

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

import sys
import os
import os.path
import re
import tempfile
import subprocess
import codecs
import unittest
import optparse
import shutil
import logging

from localized_string import LocalizedString, LocalizedStringLineParser


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
    logging.debug('Found %d files', len(code_file_paths))
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
            logging.debug('File doesnt exist, just copy')
            shutil.copy(temp_file_path, folder_path)
        os.remove(temp_file_path)
    logging.debug('done')

    shutil.rmtree(temp_folder_path)
            
def main():
    ''' Parse the command line and do what it is telled to do '''
    parser = optparse.OptionParser(
        'usage: %prog [options] Localizable.strings [source folders] [ignore patterns]'
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
        '--dry-run',
        action='store_true',
        dest='dry_run',
        default=False,
        help='Do not write to the strings file'
    )
    parser.add_option(
        '',
        '--import',
        dest='import_file',
        help='Import strings from FILENAME'
    )
    parser.add_option(
        '',
        '--overwrite',
        action='store_true',
        dest='overwrite',
        default=False,
        help='Overwrite the strings file, ignores original formatting'
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
        '',
        '--ignore',
        dest='ignore_patterns',
        help='Ignore Paths that match the patterns'
    )

    (options, args) = parser.parse_args()

    logging.basicConfig(
        format='%(message)s',
        level=options.verbose and logging.DEBUG or logging.INFO
    )

    if options.unittests:
        suite = unittest.TestLoader().loadTestsFromTestCase(Tests)
        return unittest.TextTestRunner(verbosity=2).run(suite)

    if len(args) == 0:
        parser.error('Please specify a strings file')

    strings_path = args[0]

    input_folders = ['.']
    if len(args) > 1:
        input_folders = args[1:]

    ignore_pattern = None
    if options.ignore_patterns:
        logging.debug(
            'Ignoring Patters: {}'.\
            format(options.ignore_patterns)
        )
        ignore_pattern = options.ignore_patterns

    scanned_strings = {}
    for input_folder in input_folders:
        if not os.path.isdir(input_folder):
            logging.error('Input path is not a folder: %s', input_folder)
            return 1
        # TODO: allow to specify file extensions to scan
        scanned_strings = merge_dictionaries(
            scanned_strings,
            strings_from_folder(input_folder, None, ignore_pattern)
        )
        logging.debug('Localization Tables: {}'.format(scanned_strings))
        # for tables in scanned_strings:
        #     logging.debug('Localization Table: {} with Strings: {}'.\
        #     format(tables.key, strings))
        
    reference_strings = {}
    if options.import_file:
        logging.debug(
            'Reading import file: %s',
            options.import_file
        )
        reference_strings[options.import_file] = strings_from_file(options.import_file)
        scanned_strings[options.import_file] = match_strings(
            scanned_strings[options.import_file],
            reference_strings[options.import_file]
        )
        
    strings_files = {}
    if os.path.isdir(strings_path):
        for strings_file in os.listdir(strings_path):   
            if '.strings' in strings_file:         
                logging.debug(
                    'Reading strings file: %s',
                    strings_file
                )
                strings_file_path = os.path.join(strings_path, strings_file)
                reference_strings[strings_file] = strings_from_file(
                    strings_file_path
                )
                logging.debug('ReferenceStrings:{}'.format(reference_strings[strings_file]))
                logging.debug('ScannedStrings:{}'.format(scanned_strings[strings_file]))
                # scanned_strings[strings_file] = match_strings(
                #      scanned_strings[strings_file],
                #      reference_strings[strings_file]
                #  )
                logging.debug('Ok for {}'.format(strings_file))
    else:
        logging.error('{} is not a Path'.format(strings_folder))

    if options.dry_run:
        logging.info(
            'Dry run: the strings file has not been updated'
        )
    else:
        try:
            if os.path.exists(strings_file) and not options.overwrite:
                update_file_with_strings(strings_file, scanned_strings)
            else:
                strings_to_file(scanned_strings, strings_file)
        except IOError, exc:
            logging.error('Error writing to file %s: %s', strings_file, exc)
            return 1

        logging.info(
            'Strings were generated in %s',
            strings_file
        )

    return 0

if __name__ == '__main__':
    """Run the unit- and doc-tests for the SSA module"""
    # Import and run doc-tests on doc-strings contained in this module
    logging.basicConfig(level=logging.DEBUG)
    import doctest
    doctest.testmod()
    
    
            
# if __name__ == '__main__':
#     sys.exit(main())