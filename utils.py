import pathlib, collections, __main__

# TODO OrdSet

def round_up(x, n = 1):
    return x + (n - x % n) % n

def lines_of(string):
    return [line.strip() for line in string.strip().splitlines()]

def root(*subpaths): # TODO Clean up.

    if len(subpaths) == 1 and isinstance(subpaths[0], pathlib.Path):
        return subpaths[0].absolute().relative_to(pathlib.Path.cwd(), walk_up = True)

    # Easy way to make multiple paths relative to project root.
    elif len(subpaths) == 1 and '\n' in subpaths[0]:
        return [root(path) for path in lines_of(subpaths[0])]

    # Easy way to concatenate paths together to make a path relative to project root.
    else:
        return pathlib.Path(
            pathlib.Path(__main__.__file__).absolute().parent,
            *subpaths,
        ).relative_to(pathlib.Path.cwd(), walk_up = True)

def inversing(f, xs):

    inverse = collections.defaultdict(lambda: [])

    for x in xs:
        inverse[f(x)] += [x]

    return dict(inverse)

def uniques_from(xs):
    return tuple(dict.fromkeys(xs).keys())

def nonuniques(xs):
    history = set()

    for x in xs:
        if x in history:
            return x
        else:
            history |= { x }

    return None

def ljusts(objs, keys_as_headers = False): # TODO Handle when the set of keys can vary.

    objs = tuple(objs)

    def decorator(func):

        justs = collections.defaultdict(lambda: 0)
        keys  = []

        for obj in objs:
            for key, value in func(obj).items():

                justs[key] = max(
                    justs[key],
                    len(str(value)),
                    len(key) if keys_as_headers else 0
                )

                if key not in keys:
                    keys += [key]

        def justified_func(obj):
            return {
                key : str(value).ljust(justs[key])
                for key, value in func(obj).items()
            }

        def justified_func_row(obj):
            return f'| {' | '.join(justified_func(obj).values())} |'

        justified_func.header = f'| {' | '.join(key.ljust(justs[key]) for key in keys)} |'
        justified_func.row    = justified_func_row

        return justified_func

    return decorator

def deindent(lines_or_a_string, newline_strip=True):

    if isinstance(lines_or_a_string, str):
        # Get the lines.
        lines = lines_or_a_string.splitlines()
    else:
        # Lines already given.
        lines = lines_or_a_string


    # Remove the leading newline; makes the output look closer to the multilined Python string.
    if newline_strip and lines and not lines[0].strip():
        del lines[0]


    # Deindent the lines.
    global_indent = None
    for linei, line in enumerate(lines):

        # Determine line's indent level.
        line_indent = len(line) - len(line.lstrip(' '))

        # Determine the whole text's indent level based on the first line with actual text.
        if global_indent is None and line.strip():
            global_indent = line_indent

        # Set indents appropriately.
        lines[linei] = line.removeprefix(' ' * min(line_indent, global_indent or 0))


    if isinstance(lines_or_a_string, str):
        # Give back the modified string.
        return '\n'.join(lines)
    else:
        # Give back the modified lines.
        return lines

def cstr(x):
    match x:
        case bool  () : return str(x).lower()
        case float () : return str(int(x) if x.is_integer() else x)
        case _        : return str(x)

class Obj:

    def __init__(self, __value=None, **fields):

        if __value is not None and fields:
            raise ValueError('Obj should either initialized from a value or by keyword arguments.')

        match __value:
            case None     : key_values = fields.items()
            case dict()   : key_values = __value.items()
            case Record() : key_values = __value.__dict__.items()
            case tuple()  : key_values = dict.fromkeys(__value).items()
            case list()   : key_values = dict.fromkeys(__value).items()
            case _        : raise TypeError(f"Can't make an Obj from a {type(__value)}: {__value}.")

        for key, value in key_values:
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
        return f'Obj({ ', '.join(f'{k}={v}' for k, v in self) })'


    def __contains__(self, key):
        return key in self.__dict__


class Record:

    def __init__(self, __value=None, **fields):

        if __value is not None and fields:
            raise ValueError('Record should either initialized from a value or by keyword arguments.')

        match __value:
            case None    : key_values = fields.items()
            case dict()  : key_values = __value.items()
            case Obj()   : key_values = __value.__dict__.items()
            case tuple() : key_values = dict.fromkeys(__value).items()
            case list()  : key_values = dict.fromkeys(__value).items()
            case _       : raise TypeError(f"Can't make a Record from a {type(__value)}: {__value}.")

        for key, value in key_values:
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
        return f'Record({ ', '.join(f'{k}={v}' for k, v in self) })'


    def __contains__(self, key):
        return key in self.__dict__


    def __or__(self, other):

        match other:
            case dict() : key_values = other.items()
            case Obj()  : key_values = other
            case _:
                raise TypeError(f'Record cannot be combined with a {type(other)}: {other}.')

        for key, value in key_values:
            self.__setitem__(key, value)

        return self


def Table(header, *entries):

    table = []

    for entryi, entry in enumerate(entries):

        if entry is not None: # Allows for an entry to be easily omitted.

            if len(entry) != len(header):
                raise ValueError(f'Row {entryi + 1} has {len(entry)} entries but the header defines {len(header)} columns.')

            table += [Obj(**dict(zip(header, entry)))]

    return table
