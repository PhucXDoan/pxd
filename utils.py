import types, pathlib, collections, difflib, __main__



################################################################################################################################
#
# e.g:
# >
# >    ('B', 'betty'    )
# >    ('S', 'said'     )
# >    ('S', 'she'      )
# >    ('S', 'sold'     )        ('B', ('betty', 'by'                                      ))
# >    ('S', 'seashells')   ->   ('S', ('said' , 'she', 'sold', 'seashells', 'sea', 'shore'))
# >    ('B', 'by'       )        ('T', ('the'  ,                                           ))
# >    ('T', 'the'      )
# >    ('S', 'sea'      )
# >    ('S', 'shore'    )
# >
#

def coalesce(items):

    result = collections.defaultdict(lambda: [])

    for key, value in items:
        result[key] += [value]

    return tuple((key, tuple(values)) for key, values in result.items())



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



def mk_dict(items):

    items = tuple(items)

    if (dupe := find_dupe(key for key, value in items)) is not ...:
        raise KeyError(dupe)

    return dict(items)



################################################################################################################################



def c_repr(value):
    match value:
        case bool  () : return str(value).lower()
        case float () : return str(int(value) if value.is_integer() else value)
        case None     : return 'none'
        case _        : return str(value)



################################################################################################################################



def root(*arguments):

    def mk(parts):
        return pathlib.Path(__main__.__file__).parent.joinpath(*parts).relative_to(pathlib.Path.cwd(), walk_up = True)

    match arguments:

        case [paths] if isinstance(paths, str) and '\n' in paths:
            return tuple(mk([path.strip()]) for path in paths.strip().splitlines())

        case parts:
            return mk(parts)



################################################################################################################################



def justify(rows):

    rows = tuple(tuple(row) for row in rows)



    # We will be justifying multiple columns.
    # > e.g:
    # >
    # >    for person, just_name, just_age in justify(
    # >        (
    # >            (None, person     ),
    # >            ('<' , person.name),
    # >            ('<' , person.age ),
    # >        )
    # >        for person in persons
    # >    ):
    # >        ...
    # >

    if all(
        isinstance(cell, tuple) or isinstance(cell, list)
        for row  in rows
        for cell in row
    ):
        single_column = False



    # We will be justifying only one column.
    # We will go through the same procedure as a multi-column justification
    # but the yielded value will be unpacked automatically for the user;
    # this just removes the usage of commas and parentheses a lot.
    # > e.g:
    # >
    # >    for just_name in justify(('<', person.name) for person in persons):
    # >        ...
    # >
    else:
        single_column = True
        rows          = tuple((row,) for row in rows)



    # Determine the amount of justification needed for each column.

    column_max_lengths = {
        column_i : max([0] + [
            len(str(cell_value))
            for cell_justification, cell_value in cells
            if cell_justification is not None # We will leave cells that have justification of `None` untouched.
        ])
        for column_i, cells in coalesce(
            (column_i, cell)
            for row in rows
            for column_i, cell in enumerate(row)
        )
    }



    # Justify each row.

    just_rows = []

    for row in rows:

        just_row = []

        for column_i, (cell_justification, cell_value) in enumerate(row):

            match cell_justification:
                case None : just_row += [    cell_value                                      ]
                case '<'  : just_row += [str(cell_value).ljust (column_max_lengths[column_i])]
                case '>'  : just_row += [str(cell_value).rjust (column_max_lengths[column_i])]
                case '^'  : just_row += [str(cell_value).center(column_max_lengths[column_i])]
                case _    : raise ValueError(f'Unknown justification: {repr(cell_justification)}.')

        if single_column:
            just_row, = just_row # Automatically unpack in the case of a single column.
        else:
            just_row = tuple(just_row)

        just_rows += [just_row]

    return tuple(just_rows)



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
        lines = (line.split(' ', maxsplit = global_indent)[-1] for line in lines)



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
