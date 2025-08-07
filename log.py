import contextlib, difflib



################################################################################################################################



ANSI_PROPERTIES = {
    property : tuple(f'\x1B[{code}m' for code in (enable, disable))
    for enable, disable, *properties in (
        (1  , 22, 'bold'                               ),
        (4  , 24, 'underline'                          ),
        (30 , 39, 'fg_black'         , 'black'         ),
        (31 , 39, 'fg_red'           , 'red'           ),
        (32 , 39, 'fg_green'         , 'green'         ),
        (33 , 39, 'fg_yellow'        , 'yellow'        ),
        (34 , 39, 'fg_blue'          , 'blue'          ),
        (35 , 39, 'fg_magenta'       , 'magenta'       ),
        (36 , 39, 'fg_cyan'          , 'cyan'          ),
        (37 , 39, 'fg_white'         , 'white'         ),
        (40 , 49, 'bg_black'                           ),
        (41 , 49, 'bg_red'                             ),
        (42 , 49, 'bg_green'                           ),
        (43 , 49, 'bg_yellow'                          ),
        (44 , 49, 'bg_blue'                            ),
        (45 , 49, 'bg_magenta'                         ),
        (46 , 49, 'bg_cyan'                            ),
        (47 , 49, 'bg_white'                           ),
        (90 , 39, 'fg_bright_black'  , 'bright_black'  ),
        (91 , 39, 'fg_bright_red'    , 'bright_red'    ),
        (92 , 39, 'fg_bright_green'  , 'bright_green'  ),
        (93 , 39, 'fg_bright_yellow' , 'bright_yellow' ),
        (94 , 39, 'fg_bright_blue'   , 'bright_blue'   ),
        (95 , 39, 'fg_bright_magenta', 'bright_magenta'),
        (96 , 39, 'fg_bright_cyan'   , 'bright_cyan'   ),
        (97 , 39, 'fg_bright_white'  , 'bright_white'  ),
        (100, 49, 'bg_bright_black'                    ),
        (101, 49, 'bg_bright_red'                      ),
        (102, 49, 'bg_bright_green'                    ),
        (103, 49, 'bg_bright_yellow'                   ),
        (104, 49, 'bg_bright_blue'                     ),
        (105, 49, 'bg_bright_magenta'                  ),
        (106, 49, 'bg_bright_cyan'                     ),
        (107, 49, 'bg_bright_white'                    ),
    )
    for property in properties # Some properties can go by more than one name.
}



################################################################################################################################

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
                string  = ANSI_PROPERTIES[prop][0] + string
                string += ANSI_PROPERTIES[prop][1]

            # Reenable the graphics properties we had before, if there was any.
            if log_ansi_stack:
                for prop in log_ansi_stack[-1]:
                    string += ANSI_PROPERTIES[prop][0]

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
                        indentation += ANSI_PROPERTIES[prop][0]

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
                    print(ANSI_PROPERTIES[prop][0], end = '')

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
                    print(ANSI_PROPERTIES[prop][1], end = '')

                log_ansi_stack = log_ansi_stack[:-1]

                # Reenable the old graphics configuraiton.
                for props in log_ansi_stack:
                    for prop in props:
                        print(ANSI_PROPERTIES[prop][0], end = '')

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
