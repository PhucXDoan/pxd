import contextlib, difflib

LOG_ANSI_PROPS = { prop : tuple(f'\x1B[{n}m' for n in ns) for prop, *ns in (
    ('bold'           , 1  , 22),
    ('underline'      , 4  , 24),
    ('fg_black'       , 30 , 39),
    ('fg_red'         , 31 , 39),
    ('fg_green'       , 32 , 39),
    ('fg_yellow'      , 33 , 39),
    ('fg_blue'        , 34 , 39),
    ('fg_magenta'     , 35 , 39),
    ('fg_cyan'        , 36 , 39),
    ('fg_white'       , 37 , 39),
    ('fg_bright_black', 90 , 39),
    ('bg_black'       , 40 , 49),
    ('bg_red'         , 41 , 49),
    ('bg_green'       , 42 , 49),
    ('bg_yellow'      , 43 , 49),
    ('bg_blue'        , 44 , 49),
    ('bg_magenta'     , 45 , 49),
    ('bg_cyan'        , 46 , 49),
    ('bg_white'       , 47 , 49),
    ('bg_bright_black', 100, 49),
) }

log_indent        = 0
log_starting_line = True
log_ansi_stack    = []

def log(*value, **configs):

    global log_indent, log_starting_line

    #
    # Determine if a value is provided.
    #

    if len(value) == 0:
        given_value = False
        value       = None

    elif len(value) == 1:
        given_value = True
        value       = value[0]

    else:
        raise RuntimeError(f'At most 1 non-keyword argument can be given; got {len(value)}.')

    has_configs = bool(configs)

    #
    # Get common configurations.
    #

    if (ansi := configs.pop('ansi', None)) is not None:

        # The "ansi" configuration can be a single string or a tuple of strings.
        if not isinstance(ansi, tuple):
            ansi = (ansi,)

    indent = configs.pop('indent', None)

    #
    # We assume no `with` is being used.
    #

    if given_value or not has_configs:

        # Format value into a string.
        if given_value:
            string = str(value)
        else:
            string = ''

        # Apply ANSI graphics.
        if ansi is not None:

            # Enable the new graphics properties and disable them at the end.
            for prop in ansi:
                string  = LOG_ANSI_PROPS[prop][0] + string
                string += LOG_ANSI_PROPS[prop][1]

            # Reenable the graphics properties we had before, if there was any.
            if log_ansi_stack:
                for prop in log_ansi_stack[-1]:
                    string += LOG_ANSI_PROPS[prop][0]

        # Apply indent.

        if indent:
            log_indent += 1

        if log_indent and log_starting_line:

            indentation = ' ' * 4 * log_indent

            # Clear ANSI graphics so it doesn't apply to the indentation.
            if log_ansi_stack:
                indentation = f'\x1B[0m' + indentation
                for props in log_ansi_stack:
                    for prop in props:
                        indentation += LOG_ANSI_PROPS[prop][0]

            string = indentation + string

        if indent:
            log_indent -= 1

        # Like print's "end" argument.
        string += configs.pop('end', '\n')

        # Log the string.
        print(string, end = '')

        log_starting_line = string.endswith('\n')
        result            = None

    #
    # Assuming `with` is being used.
    #

    else:

        @contextlib.contextmanager
        def ctx():

            global log_indent, log_ansi_stack

            # Push graphics configuration onto stack.
            if ansi is not None:
                log_ansi_stack += [ansi]
                for prop in log_ansi_stack[-1]:
                    print(LOG_ANSI_PROPS[prop][0], end = '')

            # Increase indent.
            if indent:
                log_indent += 1

            # User do other logging stuff.
            yield

            # Deindent.
            if indent:
                log_indent -= 1

            # Pop the graphics configuration.
            if ansi is not None:

                # Undo the latest graphics configuration.
                for prop in log_ansi_stack[-1]:
                    print(LOG_ANSI_PROPS[prop][1], end = '')

                log_ansi_stack = log_ansi_stack[:-1]

                # Reenable the old graphics configuraiton.
                for props in log_ansi_stack:
                    for prop in props:
                        print(LOG_ANSI_PROPS[prop][0], end = '')

        result = ctx()

    # There musn't be anything leftover.
    if configs:
        raise RuntimeError(f'Configurations not used: {configs}.')

    return result

def did_you_mean(message, given, options, ansi = None, tag = ''):

    if tag:
        tag += ' '

    with log(ansi = ansi):

        log(tag + message)

        if (matches := difflib.get_close_matches(given, options)):

            log(' ' * len(tag) + 'Did you mean "', end = ''               )
            log(matches[0]                       , end = '', ansi = 'bold')
            log('"?'                             ,                        )

            for match in matches[1:]:
                log(' ' * len(tag) + '          or "', end = ''               )
                log(match                            , end = '', ansi = 'bold')
                log('"?'                             ,                        )

            log(' ' * len(tag) + '       I got "', end = ''               )
            log(given                            , end = '', ansi = 'bold')
            log('".'                             ,                        )
