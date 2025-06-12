import pathlib, collections, __main__

def round_up(x, n = 1):
    return x + (n - x % n) % n

def lines_of(string):
    return [line.strip() for line in string.strip().splitlines()]

def root(*subpaths):

    # Easy way to make multiple paths relative to project root.
    if len(subpaths) == 1 and '\n' in subpaths[0]:
        return [root(path) for path in lines_of(subpaths[0])]

    # Easy way to concatenate paths together to make a path relative to project root.
    else:
        return pathlib.Path(
            pathlib.Path(__main__.__file__).absolute().relative_to(pathlib.Path.cwd(), walk_up=True).parent,
            *subpaths
        )

def inversing(f, xs):

    inverse = collections.defaultdict(lambda: [])

    for x in xs:
        inverse[f(x)] += [x]

    return dict(inverse)

def nonuniques(xs):
    history = set()

    for x in xs:
        if x in history:
            return x
        else:
            history |= { x }

    return None

def ljusts(objs):

    objs = tuple(objs)

    def decorator(func):

        justs = collections.defaultdict(lambda: 0)

        for obj in objs:
            for column, value in func(obj).items():
                justs[column] = max(justs[column], len(str(value)))

        def justified_func(obj):
            return {
                key : str(value).ljust(justs[key])
                for key, value in func(obj).items()
            }

        return justified_func

    return decorator
