import math, pathlib, builtins, collections, __main__

################################################################################################################################

def round_up(x, n = 1):
    return math.ceil(x / n) * n

################################################################################################################################

def coalesce(xs, function = None, find_dupes = False):

    inverse = collections.defaultdict(lambda: [])

    for x in xs:

        if function is None:
            key, value = x
        else:
            key, value = function(x), x

        inverse[key] += [value]

    result = { key : tuple(values) for key, values in inverse.items() }

    if find_dupes:
        result = next((
            dupes
            for dupes in result.values()
            if len(dupes) >= 2
        ), None)

    return result

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
        raise ValueError(ErrorLift(f'Making dict with duplicate key: {repr(dupe_key)}.'))

    return dict(items)

################################################################################################################################

def repr_in_c(value):
    match value:
        case bool  () : return str(value).lower()
        case float () : return str(int(value) if value.is_integer() else value)
        case None     : return 'none'
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

    elems = tuple(elems)

    if all(isinstance(elem, dict) for elem in elems):
        type = dict
    elif all(any(isinstance(elem, t) for t in (str, int)) for elem in elems):
        type  = str
        elems = tuple({ 0 : str(elem) } for elem in elems)
    else:
        type  = None
        elems = tuple({ subelem_i : subelem for subelem_i, subelem in enumerate(elem) } for elem in elems)

    justs = collections.defaultdict(lambda: 0)

    for elem in elems:
        for key, value in elem.items():
            justs[key] = max(justs[key], len(str(value)), len(str(key)) if include_keys else 0)

    elems = tuple(
        { key : str(value).ljust(justs[key]) for key, value in elem.items() }
        for elem in elems
    )

    match type:
        case builtins.str  : elems = tuple(tuple(elem.values())[0] for elem in elems)
        case builtins.dict : pass
        case None          : elems = tuple(tuple(elem.values()) for elem in elems)

    if include_keys:
        return tuple(str(key).ljust(value) for key, value in justs.items()), elems
    else:
        return elems

################################################################################################################################

def deindent(lines_or_a_string, *, remove_leading_newline = True, single_line_comment = None):

    match lines_or_a_string:
        case str() : lines = lines_or_a_string.splitlines()
        case _     : lines = list(lines_or_a_string)

    if remove_leading_newline and lines and lines[0].strip() == '':
        del lines[0]

    global_indent = None

    for line_i, line in enumerate(lines):

        line_indent = len(line) - len(line.lstrip(' '))

        if global_indent is None and line.strip() != '' and (single_line_comment is None or not line.strip().startswith(single_line_comment)):
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
            raise ValueError(ErrorLift(f'Row {entry_i + 1} has {len(entry)} entries but the header defines {len(header)} columns.'))

        table += [Obj(dict(zip(header, entry)))]

    return table

################################################################################################################################

class OrdSet:

    def __init__(self, given = ()):
        self.elems = tuple(dict.fromkeys(given).keys())

    def __repr__(self):
        if self.elems:
            return f'OrdSet({', '.join(map(repr, self.elems))})'
        else:
            return '{}'

    def __str__(self):
        return repr(self)

    def __iter__(self):
        for elem in self.elems:
            yield elem

    def __or__(self, others):
        return OrdSet((*self.elems, *others))

    def __rsub__(self, others):
        return OrdSet(other for other in others if other not in self.elems)

    def __sub__(self, others):
        return OrdSet(elem for elem in self.elems if elem not in others)

    def __getitem__(self, key):
        return self.elems[key]

    def __len__(self):
        return len(self.elems)

    def __bool__(self):
        return bool(self.elems)

    def __eq__(self, other):
        match other:
            case None : return False
            case _    : return set(self) == set(other)

################################################################################################################################

class Obj:

    def __init__(self, given = None, **fields):

        if given is not None and fields:
            raise ValueError(ErrorLift('Obj cannot be initialized using an argument and keyword-arguments at the same time.'))

        match given:
            case None     : items = fields.items()
            case dict()   : items = given.items()
            case Record() : items = given.__dict__.items()
            case tuple()  : items = dict.fromkeys(given).items()
            case list()   : items = dict.fromkeys(given).items()
            case _        : raise TypeError(ErrorLift(f'Obj can\'t be made with {type(given)}: {repr(given)}.'))

        for key, value in items:
            self.__dict__[key] = value

    def __len__(self):
        return len(self.__dict__)

    def __getattr__(self, key):
        raise AttributeError(ErrorLift(f'No field (.{key}) to read.'))

    def __setattr__(self, key, value):
        if key in self.__dict__:
            self.__dict__[key] = value
        else:
            raise AttributeError(ErrorLift(f'No field (.{key}) to write.'))

    def __getitem__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            raise AttributeError(ErrorLift(f'No field ["{key}"] to read.'))

    def __setitem__(self, key, value):
        if key in self.__dict__:
            self.__dict__[key] = value
            return value
        else:
            raise AttributeError(ErrorLift(f'No field ["{key}"] to write.'))

    def __iter__(self):
        for name, value in self.__dict__.items():
            yield (name, value)

    def __str__(self):
        return f'Obj({ ', '.join(f'{repr(key)}={repr(value)}' for key, value in self) })'

    def __repr__(self):
        return str(self)

    def __contains__(self, key):
        return key in self.__dict__

################################################################################################################################

class Record:

    def __init__(self, given = None, **fields):

        if given is not None and fields:
            raise ValueError(ErrorLift('Record cannot be initialized using an argument and keyword-arguments at the same time.'))

        match given:
            case None    : items = fields.items()
            case dict()  : items = given.items()
            case Obj()   : items = given.__dict__.items()
            case tuple() : items = dict.fromkeys(given).items()
            case list()  : items = dict.fromkeys(given).items()
            case _       : raise TypeError(ErrorLift(f'Record can\'t be made with {type(given)}: {repr(given)}.'))

        for key, value in items:
            self.__dict__[key] = value

    def __len__(self):
        return len(self.__dict__)

    def __getattr__(self, key):
        raise AttributeError(ErrorLift(f'No field (.{key}) to read.'))

    def __setattr__(self, key, value):
        if key in self.__dict__:
            raise AttributeError(ErrorLift(f'Field (.{key}) already exists.'))
        else:
            self.__dict__[key] = value

    def __getitem__(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        else:
            raise AttributeError(ErrorLift(f'No field ["{key}"] to read.'))

    def __setitem__(self, key, value):
        if key in self.__dict__:
            raise AttributeError(ErrorLift(f'Field ["{key}"] already exists.'))
        else:
            self.__dict__[key] = value
            return value

    def __iter__(self):
        for name, value in self.__dict__.items():
            yield (name, value)

    def __str__(self):
        return f'Record({ ', '.join(f'{repr(key)}={repr(value)}' for key, value in self) })'

    def __repr__(self):
        return str(self)

    def __contains__(self, key):
        return key in self.__dict__

    def __or__(self, other):

        match other:
            case dict() : items = other
            case Obj()  : items = other.__dict__
            case _:
                raise TypeError(ErrorLift(f'Record cannot be combined with a {type(other)}: {other}.'))

        return Record(**self.__dict__, **items)

################################################################################################################################

class ErrorLift(str):
    pass
