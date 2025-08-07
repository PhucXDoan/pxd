import contextlib



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



class ANSI:

    def __init__(self, value, *properties):
        self.value      = value
        self.properties = properties

    def __str__(self):

        result = str(self.value)

        for property in self.properties:

            result = (
                ANSI_PROPERTIES[property][0] +
                result                       +
                ANSI_PROPERTIES[property][1]
            )

        return result



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



    # Finally print!

    if end is ...:
        end = None

    print(value, end = end)
