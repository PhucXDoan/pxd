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
