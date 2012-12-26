# coding=utf-8

# ------------------------------------------------------------------------------
#   @author     Markus Chmelar
#   @date       2012-12-23
#   @version    1
# ------------------------------------------------------------------------------
'''
This class handels one LocalizedStrings Item

The code was originally written by the user ndfred on StackOverflow
(http://stackoverflow.com/users/303539/ndfred) and published in this post http://stackoverflow.com/questions/9895621/best-practice-using-nslocalizedstring
and then modified by me
'''
# -- Import --------------------------------------------------------------------
# Regular Expressions
import re

# -- Functions -----------------------------------------------------------------

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
            
if __name__ == '__main__':
    """Run the DocTests"""
    # Import and run doc-tests on doc-strings contained in this module
    import doctest
    doctest.testmod()