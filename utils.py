import math, pathlib, collections, __main__

################################################################################################################################

def round_up(x, n = 1):
    return math.ceil(x / n) * n

################################################################################################################################

def uniques_only(xs):
    return tuple(dict.fromkeys(xs).keys()) # Order is preserved.

################################################################################################################################

def find_dupe(xs):

    seen = set()

    for x in xs:
        if x in seen:
            return x
        else:
            seen |= { x }

    return None

################################################################################################################################

def mk_dict(items):

    items = tuple(items)

    if dupe_key := find_dupe(key for key, value in items):
        raise ValueError(f'Making dict with duplicate key: {repr(dupe_key)}.')

    return dict(items)

################################################################################################################################

def repr_in_c(value):
    match value:
        case bool  () : return str(value).lower()
        case float () : return str(int(value) if value.is_integer() else value)
        case _        : return str(value)

################################################################################################################################

def root(*paths_or_parts):

    def mk(parts):
        return pathlib.Path(__main__.__file__).parent.joinpath(*parts).relative_to(pathlib.Path.cwd(), walk_up = True)

    match paths_or_parts:

        case [paths] if isinstance(paths, str) and '\n' in paths:
            return [mk([path.strip()]) for path in paths.strip().splitlines()]

        case parts:
            return mk(parts)

################################################################################################################################

def ljusts(elems, include_keys = False):

    def decorator(func):

        justs = collections.defaultdict(lambda: 0)
        keys  = []

        for elem in elems:

            for key, value in func(elem).items():

                justs[key] = max(
                    justs[key],
                    len(str(value)),
                    len(key) if include_keys else 0,
                )

                if key not in keys:
                    keys += [key]

        def func_ljusted(elem):

            func_dict = func(elem)

            return {
                key : str(func_dict.get(key, '')).ljust(justs[key])
                for key in keys
            }

        func_ljusted.keys = tuple(key.ljust(justs[key]) for key in keys)

        return func_ljusted

    return decorator

################################################################################################################################

def deindent(lines_or_a_string, remove_leading_newline = True):

    match lines_or_a_string:
        case str() : lines = lines_or_a_string.splitlines()
        case _     : lines = lines_or_a_string

    if remove_leading_newline and lines and lines[0].strip() == '':
        del lines[0]

    global_indent = None

    for line_i, line in enumerate(lines):

        line_indent = len(line) - len(line.lstrip(' '))

        if global_indent is None and line.strip() != '':
            global_indent = line_indent

        lines[line_i] = line.removeprefix(' ' * min(line_indent, global_indent or 0))

    match lines_or_a_string:
        case str() : return '\n'.join(lines)
        case _     : return lines

################################################################################################################################

def Table(header, *entries):

    table = []

    for entry_i, entry in enumerate(entries):

        if entry is None:
            continue # Allows for an entry to be easily omitted.

        if len(entry) != len(header):
            raise ValueError(f'Row {entry_i + 1} has {len(entry)} entries but the header defines {len(header)} columns.')

        table += [Obj(dict(zip(header, entry)))]

    return table

################################################################################################################################

class Obj:

    def __init__(self, given = None, **fields):

        if given is not None and fields:
            raise ValueError('Obj cannot be initialized using an argument and keyword-arguments at the same time.')

        match given:
            case None     : items = fields.items()
            case dict()   : items = given.items()
            case Record() : items = given.__dict__.items()
            case tuple()  : items = dict.fromkeys(given).items()
            case list()   : items = dict.fromkeys(given).items()
            case _        : raise TypeError(f'Obj can\'t be made with {type(given)}: {repr(given)}.')

        for key, value in items:
            self.__dict__[key] = value

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

    def __repr__(self):
        return f'Obj({ ', '.join(f'{repr(key)}={repr(value)}' for key, value in self) })'

    def __contains__(self, key):
        return key in self.__dict__

################################################################################################################################

class Record:

    def __init__(self, given = None, **fields):

        if given is not None and fields:
            raise ValueError('Record cannot be initialized using an argument and keyword-arguments at the same time.')

        match given:
            case None    : items = fields.items()
            case dict()  : items = given.items()
            case Obj()   : items = given.__dict__.items()
            case tuple() : items = dict.fromkeys(given).items()
            case list()  : items = dict.fromkeys(given).items()
            case _       : raise TypeError(f'Record can\'t be made with {type(given)}: {repr(given)}.')

        for key, value in items:
            self.__dict__[key] = value

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

    def __repr__(self):
        return f'Record({ ', '.join(f'{repr(key)}={repr(value)}' for key, value in self) })'

    def __contains__(self, key):
        return key in self.__dict__

    def __or__(self, other):

        match other:
            case dict() : items = other.items()
            case Obj()  : items = other
            case _:
                raise TypeError(f'Record cannot be combined with a {type(other)}: {other}.')

        for key, value in items:
            self.__setitem__(key, value)

        return self
