import contextlib, types



################################################################################################################################



ANSI_PROPERTIES = { None : ('', '') } | {
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

_ansi_stack = []

class ANSI:

    def __init__(self, *arguments):
        self.arguments = arguments



    # When being used as context-manager,
    # we set up the output to have the desired ANSI graphic properties.

    def __enter__(self):

        global _ansi_stack

        _ansi_stack += self.arguments

        for property in self.arguments:
            print(ANSI_PROPERTIES[property][0], end = '')



    # At the end, we try to set the output back to the original ANSI settings.
    # We also have to re-enable everything still on the stack again
    # because the properties we just disabled might've overlapped
    # with what's still on the stack.

    def __exit__(self, *exception_info):

        global _ansi_stack

        _ansi_stack = _ansi_stack[:-len(self.arguments)]

        for property in reversed(self.arguments):
            print(ANSI_PROPERTIES[property][1], end = '')

        for property in _ansi_stack:
            print(ANSI_PROPERTIES[property][0], end = '')



    # Sometimes the class is used to quickly paint a string.
    # e.g:
    # >
    # >    log(ANSI('Red and bold!', 'fg_red', 'bold'))
    # >

    def __str__(self):

        global _ansi_stack

        value, *properties = self.arguments

        value = str(value)

        for property in properties:

            value = (
                ANSI_PROPERTIES[property][0] +
                value                        +
                ANSI_PROPERTIES[property][1]
            )

        for property in _ansi_stack: # In the event that we're in a context-manager.
            value += ANSI_PROPERTIES[property][0]

        return value



################################################################################################################################



_indent_stack = []

@contextlib.contextmanager
def Indent(characters = ' ' * 4, hanging = False):

    global _indent_stack

    _indent_stack += [types.SimpleNamespace(
        characters = characters,
        hanging     = hanging,
    )]

    yield

    _indent_stack = _indent_stack[:-1]



################################################################################################################################



def log(*arguments, end = ..., clear = False):



    # Determine how the routine is being used.

    match arguments:



        # Just log out an empty line.

        case []:
            value = ''



        # Just log out the value.

        case [value]:
            value = str(value)



        # Perform formatting on the value.
        # e.g:
        # >
        # >    log('Hello, {}. You have {} friends.', 'Ralph', 100)
        # >
        # >    log('There are {}!', ANSI('nukes incoming', 'fg_red'))
        # >

        case [value, *placeholders]:
            value = str(value).format(*placeholders)



    # Functionality to be able to clear a row and not move onto next line;
    # typically used for progress bars in CLI and such.

    if clear:

        value = '\x1B[2K\r' + value

        if end is ...: # If needed for some reason, `end` can be overridden.
            end = ''



    # Perform indentation.
    # Some indents are hanging where the characters are only printed out once
    # and the later lines are indented based on how many characters the indent was.
    # e.g:
    # >
    # >    [ERROR] This line is hanging-indented with      "[ERROR] ".
    # >            This line is now indented too, but with "        ".
    # >            This makes it easy to do multi-lined things.
    # >

    lines = value.splitlines(keepends = True)

    for line_i in range(len(lines)):

        if not lines[line_i].strip():
            continue

        for indent in reversed(_indent_stack):

            characters = indent.characters

            if indent.hanging:
                indent.characters = ' ' * len(indent.characters)

            lines[line_i] = characters + lines[line_i]

    value = ''.join(lines)



    # Finally print!

    if end is ...:
        end = None

    print(value, end = end)
