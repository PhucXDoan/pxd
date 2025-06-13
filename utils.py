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
