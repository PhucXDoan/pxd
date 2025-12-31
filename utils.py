import types, pathlib, collections, difflib, __main__



################################################################################################################################
#
# e.g:
# >
# >    find_dupe((3, 1, 4, None, 5, None, None))
# >        == None
# >
# >    find_dupe(('this', 'is', 'a', 'very', 'very', 'simple', 'example'))
# >        == 'very'
# >
# >    find_dupe(('this', 'is', 'a', 'very', 'simple', 'example'))
# >        == ...
# >
#

def find_dupe(values):

    seen = set()

    for value in values:

        if value in seen:
            return value

        seen |= { value }

    return ...



################################################################################################################################



def deindent(string, *, multilined_string_literal = True, single_line_comment = None):



    # For consistency, we preserve the newline style and whether or not the string ends with a newline.

    lines = string.splitlines(keepends = True)



    # By default, `deindent` will assume that `string` can be inputted like:
    #
    # >
    # >    deindent('''
    # >        ...
    # >    ''')
    # >
    #
    # This then means the first newline needs to be skipped.

    if multilined_string_literal and lines and lines[0].strip() == '':
        del lines[0]



    # Deindent each line of the string.

    global_indent = None

    for line in lines:



        # We currently only support space indentation.

        if line.lstrip(' ').startswith('\t'):
            raise ValueError('Only spaces for indentation is allowed.')



        # Count the leading spaces.

        line_indent = len(line) - len(line.lstrip(' '))



        # Comments shouldn't determine the indent level.

        is_comment = single_line_comment is not None and line.strip().startswith(single_line_comment)



        # Determine if this line is of interest and has the minimum amount of indentation.

        if not is_comment and line.strip():
            if global_indent is None:
                global_indent = line_indent
            else:
                global_indent = min(line_indent, global_indent)



    # Deindent each line.

    if global_indent is not None:
         lines = (line.removeprefix(' ' * min(len(line) - len(line.lstrip(' ')), global_indent)) for line in lines)



    # Rejoining the lines while preserving the newlines.

    return ''.join(lines)



################################################################################################################################



def did_you_mean(given, options):

    from ..pxd.log import log, ANSI

    if matches := difflib.get_close_matches(given, options):

        { log('Did you mean "{}"?', ANSI(matches[0], 'bold'))                          }
        { log('          or "{}"?', ANSI(match     , 'bold')) for match in matches[1:] }
        { log(' I was given "{}".', ANSI(given     , 'bold'))                          }



################################################################################################################################



def SimpleNamespaceTable(header, *entries):

    table = []

    for entry_i, entry in enumerate(entries):

        if entry is ...:
            continue # Allows for an entry to be easily omitted.

        if len(entry) != len(header):
            raise ValueError(f'Row {entry_i + 1} has {len(entry)} entries but the header defines {len(header)} columns.')

        table += [types.SimpleNamespace(**dict(zip(header, entry)))]

    return table



################################################################################################################################



class OrderedSet:



    def __init__(self, given = ()):
        self.elements = tuple(dict.fromkeys(given).keys())



    def __repr__(self):
        if self.elements:
            return f'OrderedSet({', '.join(map(repr, self.elements))})'
        else:
            return '{}'



    def __str__(self):
        return repr(self)



    def __iter__(self):
        for element in self.elements:
            yield element



    def __or__(self, others):
        return OrderedSet((*self.elements, *others))



    def __rsub__(self, others):
        return OrderedSet(other for other in others if other not in self.elements)



    def __sub__(self, others):
        return OrderedSet(element for element in self.elements if element not in others)



    def __getitem__(self, key):
        return self.elements[key]



    def __len__(self):
        return len(self.elements)



    def __bool__(self):
        return bool(self.elements)



    def __eq__(self, other):
        match other:
            case None : return False
            case _    : return set(self) == set(other)



################################################################################################################################



class ContainedNamespace:



    def __init__(self, given = None, **fields):

        if given is not None and fields:
            raise ValueError('Cannot initialize using an argument and keyword-arguments at the same time.')

        match given:
            case None                  : items = fields.items()
            case dict()                : items = given.items()
            case AllocatingNamespace() : items = given.__dict__.items()
            case tuple()               : items = dict.fromkeys(given).items()
            case list()                : items = dict.fromkeys(given).items()
            case _                     : raise TypeError(f'Unsupported type: {type(given)}.')

        for key, value in items:
            self.__dict__[key] = value



    def __len__(self):
        return len(self.__dict__)



    def __getattr__(self, key):
        raise AttributeError(f'No field (.{key}) to read.')



    def __setattr__(self, key, value):
        if key in self.__dict__:
            self.__dict__[key] = value
        else:
            raise AttributeError(f'No field (.{key}) to write.')



    def __getitem__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            raise AttributeError(f'No field ["{key}"] to read.')



    def __setitem__(self, key, value):
        if key in self.__dict__:
            self.__dict__[key] = value
            return value
        else:
            raise AttributeError(f'No field ["{key}"] to write.')



    def __iter__(self):
        for name, value in self.__dict__.items():
            yield (name, value)



    def __str__(self):
        return f'ContainedNamespace({ ', '.join(f'{repr(key)}={repr(value)}' for key, value in self) })'



    def __repr__(self):
        return str(self)



    def __contains__(self, key):
        return key in self.__dict__



################################################################################################################################



class AllocatingNamespace:



    def __init__(self, given = None, **fields):

        if given is not None and fields:
            raise ValueError('Cannot initialize using an argument and keyword-arguments at the same time.')

        match given:
            case None                 : items = fields.items()
            case dict()               : items = given.items()
            case ContainedNamespace() : items = given.__dict__.items()
            case tuple()              : items = dict.fromkeys(given).items()
            case list()               : items = dict.fromkeys(given).items()
            case _                    : raise TypeError(f'Unsupported type: {type(given)}.')

        for key, value in items:
            self.__dict__[key] = value



    def __len__(self):
        return len(self.__dict__)



    def __getattr__(self, key):
        raise AttributeError(f'No field (.{key}) to read.')



    def __setattr__(self, key, value):
        if key in self.__dict__:
            raise AttributeError(f'Field (.{key}) already exists.')
        else:
            self.__dict__[key] = value



    def __getitem__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            raise AttributeError(f'No field ["{key}"] to read.')



    def __setitem__(self, key, value):
        if key in self.__dict__:
            raise AttributeError(f'Field ["{key}"] already exists.')
        else:
            self.__dict__[key] = value
            return value



    def __iter__(self):
        for name, value in self.__dict__.items():
            yield (name, value)



    def __str__(self):
        return f'AllocatingNamespace({ ', '.join(f'{repr(key)}={repr(value)}' for key, value in self) })'



    def __repr__(self):
        return str(self)



    def __contains__(self, key):
        return key in self.__dict__



    def __or__(self, other):

        match other:
            case dict()               : items = other
            case ContainedNamespace() : items = other.__dict__
            case _                    : raise TypeError(f'Unsupported type: {type(other)}.')

        return AllocatingNamespace(**self.__dict__, **items)
