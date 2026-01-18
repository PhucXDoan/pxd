################################################################################
#
# Enforce Python version.
#



import sys

MINIMUM_MAJOR = 3
MINIMUM_MINOR = 13

if not (
    sys.version_info.major == MINIMUM_MAJOR and
    sys.version_info.minor >= MINIMUM_MINOR
):
    raise RuntimeError(
        'Unsupported Python version: ' + repr(sys.version) + '; ' +
        'please upgrade to at least ' + str(MINIMUM_MAJOR) + '.' + str(MINIMUM_MINOR) + '; '
        'note that it is possible that you have multiple instances of Python installed; '
        'in this case, please set your PATH accordingly or use a Python virtual environment.'
    )



################################################################################
#
# Built-in modules.
#



import types, builtins, collections, pathlib, re, string
import logging, difflib, time
import shlex, subprocess
import contextlib
import ast, traceback
import __main__



################################################################################
#
# Routine to find keys with common values.
#



def coalesce(key_value_pairs):

    pool = collections.defaultdict(lambda: [])

    for key, value in key_value_pairs:
        pool[key] += [value]

    return tuple(pool.items())



################################################################################
#
# Routine to justify columns of values.
#



def justify(rows):

    rows = tuple(tuple(row) for row in rows)



    # Determine the amount of justification needed for each column.

    column_max_lengths = {

        column_i : max([
            len(str(value))
            for justification, value in cells
            if justification is not None
        ] or [0])

        for column_i, cells in coalesce(
            (column_i, cell)
            for row in rows
            for column_i, cell in enumerate(row)
        )

    }



    # Justify each row.

    just_rows = []

    for row in rows:

        just_row = []

        for column_i, (justification, value) in enumerate(row):

            match justification:
                case None : just_row += [    value                                      ]
                case '<'  : just_row += [str(value).ljust (column_max_lengths[column_i])]
                case '>'  : just_row += [str(value).rjust (column_max_lengths[column_i])]
                case '^'  : just_row += [str(value).center(column_max_lengths[column_i])]
                case _    : raise ValueError(f'Unknown justification: {repr(justification)}.')

        just_rows += [just_row]

    return just_rows



################################################################################
#
# ANSI graphics constants.
#



ANSI_RESET              = '\x1B[0m'
ANSI_BOLD               = '\x1B[1m'
ANSI_UNDERLINE          = '\x1B[4m'
ANSI_FG_BLACK           = '\x1B[30m'
ANSI_FG_RED             = '\x1B[31m'
ANSI_FG_GREEN           = '\x1B[32m'
ANSI_FG_YELLOW          = '\x1B[33m'
ANSI_FG_BLUE            = '\x1B[34m'
ANSI_FG_MAGENTA         = '\x1B[35m'
ANSI_FG_CYAN            = '\x1B[36m'
ANSI_FG_WHITE           = '\x1B[37m'
ANSI_FG_BRIGHT_BLACK    = '\x1B[90m'
ANSI_FG_BRIGHT_RED      = '\x1B[91m'
ANSI_FG_BRIGHT_GREEN    = '\x1B[92m'
ANSI_FG_BRIGHT_YELLOW   = '\x1B[93m'
ANSI_FG_BRIGHT_BLUE     = '\x1B[94m'
ANSI_FG_BRIGHT_MAGENTA  = '\x1B[95m'
ANSI_FG_BRIGHT_CYAN     = '\x1B[96m'
ANSI_FG_BRIGHT_WHITE    = '\x1B[97m'
ANSI_BG_BLACK           = '\x1B[40m'
ANSI_BG_RED             = '\x1B[41m'
ANSI_BG_GREEN           = '\x1B[42m'
ANSI_BG_YELLOW          = '\x1B[43m'
ANSI_BG_BLUE            = '\x1B[44m'
ANSI_BG_MAGENTA         = '\x1B[45m'
ANSI_BG_CYAN            = '\x1B[46m'
ANSI_BG_WHITE           = '\x1B[47m'
ANSI_BG_BRIGHT_BLACK    = '\x1B[100m'
ANSI_BG_BRIGHT_RED      = '\x1B[101m'
ANSI_BG_BRIGHT_GREEN    = '\x1B[102m'
ANSI_BG_BRIGHT_YELLOW   = '\x1B[103m'
ANSI_BG_BRIGHT_BLUE     = '\x1B[104m'
ANSI_BG_BRIGHT_MAGENTA  = '\x1B[105m'
ANSI_BG_BRIGHT_CYAN     = '\x1B[106m'
ANSI_BG_BRIGHT_WHITE    = '\x1B[107m'



################################################################################
#
# Routine to add a jutsified table to a log message.
#


def append_log_table(message, record):

    if hasattr(record, 'table'):

        for just_key, just_value in justify([
            (
                ('<' , str(key  )),
                (None, str(value)),
            )
            for key, value in record.table
        ]):
            message += f'\n{just_key} : {just_value}'

    return message



################################################################################
#
# Routine to format a log to indicate its severity.
#



def prepend_log_level(message, record):

    indent = ' ' * len(f'[{record.levelname}] ')

    message = '\n'.join([
        (message.splitlines() or [''])[0],
        *[f'{indent}{line}' for line in message.splitlines()[1:]]
    ])

    coloring = {
        'DEBUG'    : ANSI_FG_MAGENTA,
        'INFO'     : ANSI_FG_CYAN,
        'WARNING'  : ANSI_FG_YELLOW,
        'ERROR'    : ANSI_FG_RED,
        'CRITICAL' : ANSI_FG_RED + ANSI_BOLD,
    }[record.levelname]

    message = f'{ANSI_RESET}{coloring}[{record.levelname}]{ANSI_RESET} {message}'

    return message



################################################################################
#
# Top-level default logger.
#



class MainFormatter(logging.Formatter):

    def format(self, record):

        message  = super().format(record)
        message  = append_log_table(message, record)
        message  = prepend_log_level(message, record)
        message += '\n'

        return message



pxd_logger         = logging.getLogger(__name__)
pxd_logger_handler = logging.StreamHandler(sys.stdout)
pxd_logger_handler.setFormatter(MainFormatter())
pxd_logger.addHandler(pxd_logger_handler)
pxd_logger.setLevel(logging.DEBUG)



################################################################################
#
# Routine to create main script relative paths.
#



def make_main_relative_path(*parts):

    return (
        pathlib.Path(__main__.__file__)
            .parent
            .joinpath(*parts)
            .relative_to(pathlib.Path.cwd(), walk_up = True)
    )



################################################################################
#
# Routine to give good diagnostics for a set of options.
#



def did_you_mean(message, given, options):

    suggestions = difflib.get_close_matches(
        given,
        [str(option) for option in options],
    )

    message += '\n'

    for suggestion_i, suggestion in enumerate(suggestions):
        line     = '... or {}?' if suggestion_i else 'Did you mean {}?'
        line     = ' ' * (message.index('{}') - line.index('{}')) + line
        message += line + '\n'

    message = message.format(
        repr(given),
        *[repr(suggestion) for suggestion in suggestions]
    ).removesuffix('\n')

    return message



################################################################################
#
# Routine to carry out shell commands.
#



class ExecuteShellCommandNonZeroExitCode(Exception):
    pass



def execute_shell_command(
    default    = None,
    *,
    bash       = None,
    cmd        = None,
    powershell = None,
    logger     = pxd_logger,
):



    # PowerShell is slow to invoke, so cmd.exe
    # would be used if its good enough.

    if cmd is not None and powershell is not None:
        raise ValueError('CMD and PowerShell commands cannot be both provided.')

    match sys.platform:

        case 'win32':
            use_powershell = cmd is None and powershell is not None
            commands       = powershell if use_powershell else cmd

        case _:
            commands       = bash
            use_powershell = False

    if commands is None:
        commands = default

    if commands is None:
        raise ValueError(f'Missing shell command for platform {repr(sys.platform)}.')

    if isinstance(commands, str):
        commands = [commands]



    # Process each command to have it be split into shell tokens.
    # The lexing that's done here is to do a lot of the funny
    # business involving escaping quotes and what not. To be honest,
    # it's a little out my depth, mainly because I frankly do not
    # care enough to get it 100% correct; it working most of the time
    # is good enough for me.

    for command_i in range(len(commands)):

        lexer                  = shlex.shlex(commands[command_i])
        lexer.quotes           = '"'
        lexer.whitespace_split = True
        lexer.commenters       = ''
        commands[command_i]    = ' '.join(list(lexer))



    # Execute each shell command.

    processes = []

    for command_i, command in enumerate(commands):

        if logger:
            logger.info(f'$ {command}')

        if use_powershell:

            # On Windows, Python will call CMD.exe
            # to run the shell command, so we'll
            # have to invoke PowerShell to run the
            # command if PowerShell is needed.

            processes += [subprocess.Popen(['pwsh', '-Command', command], shell = False)]

        else:

            processes += [subprocess.Popen(
                command,
                shell  = True,
                stdout = subprocess.PIPE if len(commands) >= 2 else None,
                stderr = subprocess.PIPE if len(commands) >= 2 else None,
            )]



    # Wait on each subprocess to be done.

    non_zero_exit_code_found = False

    for process in processes:

        if process.wait():

            non_zero_exit_code_found = True

            if len(commands) >= 2:

                if logger:
                    logger.error(f'$ {command}')



                # TODO Not optimal that we're using print here,
                # but working with `subprocess.Popen`'s output
                # is pretty tricky unfortunately, and I don't
                # have time for it.

                for line in process.stdout:
                    print(line.decode('UTF-8'), end = '')

                for line in process.stderr:
                    print(line.decode('UTF-8'), end = '')

            print()



    if non_zero_exit_code_found:
        raise ExecuteShellCommandNonZeroExitCode



################################################################################
#
# Command-line interface builder.
#



class CommandLineInterface:



    # Interfaces are where all verbs are
    # grouped together and are eventually invoked.

    def __init__(
        self,
        *,
        name        = ...,
        description = ...,
        logger      = ...,
        hook        = ...,
    ):



        if name is ...:
            name = f'{make_main_relative_path(pathlib.Path(__main__.__file__).name)}'

        self.name = name



        if description is ...:
            description = f'The {repr(pathlib.Path(__main__.__file__).name)} command line program.'

        self.description = description



        if logger is ...:

            class CommandLineInterfaceFormatter(logging.Formatter):

                def format(self, record):

                    message = super().format(record)
                    message = append_log_table(message, record)

                    if record.levelname != 'INFO':
                        message = prepend_log_level(message, record)

                    message += '\n'

                    return message

            logger         = logging.getLogger('pxd_CommandLineInterface')
            logger_handler = logging.StreamHandler(sys.stdout)
            logger_handler.setFormatter(CommandLineInterfaceFormatter())
            logger.addHandler(logger_handler)
            logger.setLevel(logging.DEBUG)

        self.logger = logger



        if hook is ...:

            def default_hook(verb, parameters):

                start   = time.time()
                yield
                end     = time.time()
                elapsed = end - start

                if elapsed >= 0.5:
                    self.logger.debug(f'"{verb.name}" took {elapsed :.3f}s.')

            hook = default_hook

        self.hook = hook



        self.verbs = []
        self.new_verb(
            {
                'description' : f"Show usage of {repr(self.name)}; pass 'all' for all details."
            },
            {
                'name'        : 'verb_name',
                'description' : 'Name of the verb to show more detail on.',
                'type'        : str,
                'default'     : None,
            }
        )(self.help)



    # The default help verb.

    def help(self, parameters):

        output = ''



        # Details of the interface itself.

        output += f'> {ANSI_UNDERLINE}{ANSI_BOLD}{self.name} [verb] (parameters...){ANSI_RESET}' '\n'
        output += f'{self.description}'                                                          '\n'
        output += '\n'



        # We want to show the `help` last so that
        # it'll be the first thing the user sees
        # if the list of verbs is very long.

        shown_verbs = sorted(
            [
                verb
                for verb in self.verbs
                if parameters.verb_name in (verb.name, None, 'all')
            ],
            key = lambda verb: (verb.name == 'help')
        )



        # If given a specific verb name as a parameter,
        # make sure it actually exists.

        if not shown_verbs and parameters.verb_name not in (None, 'all'):

            self.help(types.SimpleNamespace(
                verb_name = None,
            ))

            self.logger.error(did_you_mean(
                'No verb goes by the name of {}.',
                parameters.verb_name,
                [verb.name for verb in self.verbs],
            ))

            sys.exit(1)



        # Details of each verb registered in the interface.

        for verb in shown_verbs:



            # Indicator to show that some verbs were filtered out.

            verbs_were_filtered_out = parameters.verb_name not in (None, 'all')

            if verbs_were_filtered_out:
                output += '    ...' '\n'
                output += '\n'



            # Verb name.

            output += f'    > {ANSI_UNDERLINE}{ANSI_BOLD}{self.name} {ANSI_FG_GREEN}{verb.name}{ANSI_RESET}{ANSI_UNDERLINE}{ANSI_BOLD}'



            # Verb parameters in the invocation.

            for parameter_schema in verb.parameter_schemas:

                output += f' {parameter_schema.formatted_name}'

            output += f'{ANSI_RESET}' '\n'



            # Verb description.

            output += f'    {verb.description}' '\n'
            output += '\n'



            # Verb parameter descriptions.

            if parameters.verb_name is not None:



                # Default breakdown of the different
                # parameters that the verb takes as inputs.

                for parameter_schema in verb.parameter_schemas:

                    output += f'        {parameter_schema.formatted_name} {parameter_schema.description}' '\n'



                    # Show that the parameter is optional if applicable.

                    if parameter_schema.has_default:

                        match parameter_schema.default:

                            case str() | int() | float() | bool():
                                default = repr(parameter_schema.default)

                            case _: # Not easily representable.
                                default = '(optional)'

                        output += f'            = {default}' '\n'



                    # If the parameter is a list of options,
                    # list them all out here.

                    match parameter_schema.type:

                        case list() | tuple() | dict():

                            for option in parameter_schema.type:

                                output += f'            - {repr(option)}\n'



                    output += '\n'



                # The verb can supply additional
                # information at run-time.

                if verb.more_help:

                    output += '\n'.join(
                        f'        {line}'
                        for line in verb.function(None).splitlines()
                    ) + '\n'

                    output += '\n'



            # Indicator to show that some verbs were filtered out.

            if verbs_were_filtered_out:
                output += '    ...' '\n'
                output += '\n'



        output = output.removesuffix('\n')

        self.logger.info(output)



    # Routine for registering new verbs to the interface.

    def new_verb(self, properties_of_verb, *properties_of_parameters):

        def decorator(function):



            # Process verb properties.

            verb_name        = properties_of_verb.pop('name', None)
            verb_description = properties_of_verb.pop('description')
            verb_more_help   = properties_of_verb.pop('more_help', False)

            if verb_name is None:
                verb_name = function.__name__

            if not verb_name.isidentifier():
                raise ValueError(
                    f'Verb name {repr(verb_name)} must be an identifier.'
                )

            if verb_name == 'all':
                raise ValueError(
                    f"Verb name {repr(verb_name)} cannot be 'all'."
                )

            if properties_of_verb:
                raise ValueError(
                    f'Leftover verb properties: {repr(properties_of_verb)}.'
                )

            if any(verb_name == past_verb.name for past_verb in self.verbs):
                raise ValueError(
                    f'Verb name {repr(verb_name)} already used.'
                )



            # Process parameter properties.

            parameter_schemas = []

            for parameter_property in properties_of_parameters:



                # Validate the properties.

                parameter_identifier_name = parameter_property.pop('name')
                parameter_description     = parameter_property.pop('description')
                parameter_type            = parameter_property.pop('type')
                parameter_has_default     = parameter_property.get('default', ...) is not ...
                parameter_default         = parameter_property.pop('default', None)
                parameter_flag_only       = parameter_property.pop('flag_only', None)

                if not parameter_identifier_name.isidentifier():
                    raise ValueError(
                        f'Parameter name {repr(parameter_identifier_name)} must be an identifier.'
                    )

                if parameter_property:
                    raise ValueError(
                        f'Leftover parameter properties: {repr(parameter_property)}.'
                    )



                # Boolean parameters will default to being flag-only.

                if parameter_type == bool and parameter_flag_only is None:
                    parameter_flag_only = True



                # Determine the formatted name.

                parameter_formatted_name = f'{parameter_identifier_name.replace('_', '-')}'

                if parameter_flag_only:
                    parameter_formatted_name = f'--{parameter_formatted_name}'

                if not parameter_has_default:
                    parameter_formatted_name = f'*{parameter_formatted_name}'

                parameter_formatted_name = f'({parameter_formatted_name})'



                # The verb now has a new parameter.

                parameter_schemas += [types.SimpleNamespace(
                    identifier_name = parameter_identifier_name,
                    formatted_name  = parameter_formatted_name,
                    flag_name       = parameter_identifier_name.replace('_', '-'),
                    description     = parameter_description,
                    type            = parameter_type,
                    has_default     = parameter_has_default,
                    default         = parameter_default,
                    flag_only       = parameter_flag_only,
                )]



            # Register the new verb.

            self.verbs += [types.SimpleNamespace(
                name              = verb_name,
                description       = verb_description,
                more_help         = verb_more_help,
                parameter_schemas = parameter_schemas,
                function          = function,
            )]

            return function

        return decorator



    # Given some arguments, call onto the
    # appropriate verb with the parsed parameters.

    def invoke(self, given = ...):



        # Most of the time the interface will be called with
        # the Python script's command line arguments.

        if given is ...:

            try:

                self.invoke(sys.argv[1:])
                sys.exit(0)

            except KeyboardInterrupt:

                self.logger.error('Interrupted by keyboard.')
                sys.exit(1)

            except ExecuteShellCommandNonZeroExitCode:

                self.logger.error('Shell command exited with non-zero exit code.')
                sys.exit(1)



        # Just show the help information if given no arguments.

        if not given:

            self.help(types.SimpleNamespace(
                verb_name = None,
            ))

            return



        # Search for the verb.

        given_verb_name, *remaining_arguments = given

        for verb in self.verbs:
            if verb.name == given_verb_name:
                break

        else:

            self.help(types.SimpleNamespace(
                verb_name = None,
            ))

            self.logger.error(did_you_mean(
                'No verb goes by the name of {}.',
                given_verb_name,
                [verb.name for verb in self.verbs],
            ))

            sys.exit(1)

        # Arguments can either be unnamed or be specified as flags.

        def flag_split(argument):



            # Argument needs the flag prefix.

            if not argument.startswith('--'):
                return (None, argument)



            # The flag argument may have an
            # assigned value associated with it.

            flag_name, *flag_value = argument.removeprefix('--').split('=', 1)

            if flag_value == []:
                flag_value = None
            else:
                flag_value, = flag_value



            # The flag name must look like a proper name.

            if not flag_name.replace('-', '_').isidentifier():
                return (None, argument)



            return (flag_name, flag_value)



        # Arguments that are given as flags are prioritized.

        parameters                  = {}
        remaining_parameter_schemas = verb.parameter_schemas[:]
        remaining_arguments         = [flag_split(argument) for argument in remaining_arguments]

        for flag_name, flag_value in remaining_arguments:

            if flag_name is None:
                continue



            # Look for parameter of the same flag name.

            for parameter_schema_i, parameter_schema in enumerate(verb.parameter_schemas):
                if parameter_schema.flag_name == flag_name:
                    break



            # Couldn't find a parameter that match the flag argument.

            else:

                self.help(types.SimpleNamespace(
                    verb_name = verb.name,
                ))

                self.logger.error(did_you_mean(
                    'Unknown parameter flag {}.',
                    flag_name,
                    [
                        parameter_schema.flag_name
                        for parameter_schema in verb.parameter_schemas
                    ],
                ))

                sys.exit(1)



            # Ensure all flag arguments are unique.

            if flag_name in parameters:

                self.logger.error(
                    f'Parameter {parameter_schema.formatted_name} already given.'
                )

                sys.exit(1)



            # Only boolean flags can have unassigned values.

            if flag_value is None:

                if parameter_schema.type == bool:

                    flag_value = 'true'

                else:

                    self.logger.error(
                        f'Parameter {parameter_schema.formatted_name} '
                        f'must be given a flag value.'
                    )

                    sys.exit(1)



            # We've now processed the flag argument and parameter.

            parameters[parameter_schema.identifier_name] = flag_value

            del remaining_parameter_schemas[parameter_schema_i]



        # Rest of the remaining arguments are unnamed.

        remaining_arguments = [
            flag_value
            for flag_name, flag_value in remaining_arguments
            if flag_name is None
        ]



        # Pair up the remaining parameters and arguments.

        while remaining_parameter_schemas and remaining_arguments:



            # Some parameters can only be provided as flags.

            if remaining_parameter_schemas[0].flag_only:

                self.logger.error(
                    f'Parameter {remaining_parameter_schemas[0].formatted_name} '
                    f'must be provided as a flag.'
                )

                sys.exit(1)



            parameters[remaining_parameter_schemas[0].identifier_name] = remaining_arguments[0]

            del remaining_parameter_schemas[0]
            del remaining_arguments[0]



        # There shouldn't be any leftover arguments.

        if remaining_arguments:

            self.help(types.SimpleNamespace(
                verb_name = verb.name,
            ))

            self.logger.error(f'Extra argument {repr(remaining_arguments[0])}.')

            sys.exit(1)



        # Determine each parameter's final value.

        for parameter_schema in verb.parameter_schemas:



            # Parse the parameter value given by the user.

            if parameter_schema.identifier_name in parameters:

                value = parameters[parameter_schema.identifier_name]

                match parameter_schema.type:



                    # Strings stay as-is.

                    case builtins.str:
                        pass



                    # Interpret as an integer.

                    case builtins.int:

                        try:

                            value = int(value)

                        except ValueError:

                            self.help(types.SimpleNamespace(
                                verb_name = verb.name,
                            ))

                            self.logger.error(
                                f'Parameter {parameter_schema.formatted_name} must be an integer; '
                                f'got {repr(value)}.'
                            )

                            sys.exit(1)



                    # Interpret as a boolean.

                    case builtins.bool:

                        FALSY  = ('0', 'f', 'n', 'no' , 'false')
                        TRUTHY = ('1', 't', 'y', 'yes', 'true' )

                        value = value.lower()

                        if value in FALSY:
                            value = False

                        elif value in TRUTHY:
                            value = True

                        else:

                            self.logger.error(
                                f'Parameter {parameter_schema.formatted_name} must be a boolean; '
                                f'can be {repr(FALSY)} or {repr(TRUTHY)}.'
                            )

                            sys.exit(1)



                    # Pick from a list of options.

                    case list() | tuple() | dict():



                        options = parameter_schema.type

                        if isinstance(parameter_schema.type, dict):
                            options = list(parameter_schema.type.keys())



                        if value not in options:

                            self.help(types.SimpleNamespace(
                                verb_name = verb.name,
                            ))

                            self.logger.error(did_you_mean(
                                f'Parameter {parameter_schema.formatted_name} '
                                f'given invalid option of {{}}.',
                                value,
                                options,
                            ))

                            sys.exit(1)



                        if isinstance(parameter_schema.type, dict):
                            value = parameter_schema.type[value]



                    # Unknown parameter type.

                    case idk:
                        raise TypeError(f'Unsupported parameter type: {repr(idk)}.')



                parameters[parameter_schema.identifier_name] = value



            # The user didn't provide this parameter,
            # but at least there's a fallback value.

            elif parameter_schema.has_default:

                parameters[parameter_schema.identifier_name] = parameter_schema.default



            # Missing required parameter.

            else:

                self.help(types.SimpleNamespace(
                    verb_name = verb.name,
                ))

                self.logger.error(f'Missing parameter {parameter_schema.formatted_name}.')

                sys.exit(1)



        # Begin the hook.

        hook_iterator = None

        if self.hook:

            hook_iterator = self.hook(verb, parameters)

            if not isinstance(hook_iterator, types.GeneratorType):
                raise ValueError(f'Hook must be a generator.')

            try:
                next(hook_iterator)
            except StopIteration as error:
                raise RuntimeError(f'Hook did not yield.') from error



        # Finally execute the verb.

        verb.function(types.SimpleNamespace(**parameters))



        # End the hook.

        if self.hook:

            stopped = False

            try:
                next(hook_iterator)
            except StopIteration:
                stopped = True

            if not stopped:
                raise RuntimeError('Hook did not return.')



################################################################################
#
# Routine to convert Python values into something C-like.
#



def c_repr(value):

    match value:
        case bool  () : return str(value).lower()
        case float () : return str(int(value) if value.is_integer() else value)
        case None     : return 'none'
        case _        : return str(value)



################################################################################
#
# Routine to set the indentation of multi-lined text.
#



def deindent(
    string,
    *,
    multilined_string_literal = True,
    single_line_comment       = None,
    indent                    = '',
):



    # For consistency, we preserve the newline style and
    # whether or not the string ends with a newline.

    lines = string.splitlines(keepends = True)



    # By default, `deindent` will assume
    # that `string` can be inputted like:
    #
    # >
    # >    deindent('''
    # >        ...
    # >    ''')
    # >
    #
    # This then means the first newline needs to be skipped.

    if multilined_string_literal and lines and lines[0].strip() == '':
        lines = lines[1:]



    # Deindent each line of the string.

    global_indent = None

    for line in lines:



        # We currently only support space indentation.

        if line.lstrip(' ').startswith('\t'):
            raise ValueError('Only spaces for indentation is allowed.')



        # Count the leading spaces.

        line_indent = len(line) - len(line.lstrip(' '))



        # Comments shouldn't determine the indent level.

        is_comment = (
            single_line_comment is not None and
            line.strip().startswith(single_line_comment)
        )



        # Determine if this line is of interest and
        # has the minimum amount of indentation.

        if not is_comment and line.strip():
            if global_indent is None:
                global_indent = line_indent
            else:
                global_indent = min(line_indent, global_indent)



    # Deindent each line.

    if global_indent is not None:

        lines = (
            ('' if line.strip() == '' else indent) +
            line.removeprefix(' ' * min(len(line) - len(line.lstrip(' ')), global_indent))
            for line in lines
        )



    # Rejoining the lines while preserving the newlines.

    return ''.join(lines)



################################################################################
#
# Routine to create list of SimpleNamespaces in a table-like syntax.
#



def SimpleNamespaceTable(header, *entries):

    table = []

    for entry_i, entry in enumerate(entries):

        if entry is ...:
            continue # Allows for an entry to be easily omitted.

        if len(entry) != len(header):
            raise ValueError(
                f'Row {entry_i + 1} has {len(entry)} entries '
                f'but the header defines {len(header)} columns.'
            )

        table += [types.SimpleNamespace(**dict(zip(header, entry)))]

    return table



################################################################################
#
# Meta-preprocessor.
#



class MetaPreprocessorError(Exception):
    pass



def metapreprocess(*,
    output_directory_path,
    source_file_paths,
    callback = ...,
    logger   = ...,
):



    # Process the parameters.

    output_directory_path = pathlib.Path(output_directory_path)
    source_file_paths     = [
        pathlib.Path(source_file_path)
        for source_file_path in source_file_paths
    ]



    # Provide the default logger that'll give good diagnostics.

    if logger is ...:

        class MetaPreprocessorFormatter(logging.Formatter):

            def format(self, record):



                # Some basic, common formattings.

                message = super().format(record)
                message = append_log_table(message, record)
                message = prepend_log_level(message, record)



                # To give good error messages, we'll display
                # the locations of the lines that are causing
                # the issue.

                if hasattr(record, 'frames'):

                    frame_lines = []
                    gutter      = ''

                    for frame in record.frames:
                        CONTEXT_MARGIN          = 3
                        frame.source_file_lines = frame.source_file_path.read_text().splitlines()
                        frame.minimum_index     = max(frame.line_number - 1 - CONTEXT_MARGIN, 0)
                        frame.maximum_index     = min(frame.line_number - 1 + CONTEXT_MARGIN, len(frame.source_file_lines) - 1)
                        gutter                  = ' ' * max(len(gutter), len(repr(frame.maximum_index + 1)))

                    for frame_i, frame in enumerate(record.frames):



                        # Small margin to give breathing room.

                        if frame_i == 0:
                            frame_lines += [f'{gutter} |']



                        # Have a little divider to show separate frame contexts.

                        else:
                            frame_lines += [
                                f'{gutter} :',
                                f'{gutter} : {ANSI_FG_BRIGHT_BLACK}{'.' * 80}{ANSI_RESET}',
                                f'{gutter} :',
                            ]



                        # Grab some lines from the source code near the error.

                        for source_line_index in range(frame.minimum_index, frame.maximum_index + 1):

                            frame_line = f'{repr(source_line_index + 1).rjust(len(gutter))} | '

                            if source_line_index + 1 == frame.line_number:
                                frame_line += ANSI_BG_RED + ANSI_BOLD

                            frame_line += frame.source_file_lines[source_line_index]

                            if source_line_index + 1 == frame.line_number:
                                frame_line += ANSI_RESET
                                frame_line += ANSI_FG_BRIGHT_YELLOW
                                frame_line += f' <- {frame.source_file_path.as_posix()} : {frame.line_number}'
                                frame_line += ANSI_RESET

                            frame_lines += [frame_line]



                        # Last frame, so insert some breathing room.

                        if frame_i == len(record.frames) - 1:

                            frame_lines += [f'{gutter} |']



                    # Put all the selected lines together
                    # to have a nice diagnostic.

                    message = '\n'.join(frame_lines) + ('\n' * 2) + message



                message += '\n'

                return message



        logger         = logging.getLogger('pxd_MetaPreprocessor')
        logger_handler = logging.StreamHandler(sys.stdout)
        logger_handler.setFormatter(MetaPreprocessorFormatter())
        logger.addHandler(logger_handler)
        logger.setLevel(logging.DEBUG)



    # Provide the default callback that'll give timing metrics.

    elapsed               = 0
    meta_directive_deltas = []

    def default_callback(meta_directives, meta_directive_i):

        nonlocal elapsed, meta_directive_deltas

        meta_directive = meta_directives[meta_directive_i]



        # Log the evaluation of the meta-directive.

        location = f'{meta_directive.source_file_path.as_posix()}:{meta_directive.first_header_line_number}'

        logger.info(f'Meta-preprocessing {location}')



        # Record how long it takes to run this meta-directive.

        start                  = time.time()
        output                 = yield
        end                    = time.time()
        delta                  = end - start
        meta_directive_deltas += [(location, delta)]
        elapsed               += delta



    if callback is ...:
        callback = default_callback



    # Find all meta-directives.

    meta_directives = []

    for source_file_path in source_file_paths:

        remaining_lines = source_file_path.read_text().splitlines()
        total_lines     = len(remaining_lines)

        while remaining_lines:

            meta_directive = types.SimpleNamespace(
                source_file_path         = source_file_path,
                include_file_path        = None,
                include_line_number      = None,
                first_header_line_number = None,
                identifiers              = [],
                body_line_number         = None,
                body_lines               = [],
                meta_main_line_number    = None,
            )



            # Parse for any include-directives that may prepend a meta-directive.

            while remaining_lines:

                include_match = (
                    re.match(r'\s*#\s*include\s*"(.*)"', remaining_lines[0]) or
                    re.match(r'\s*#\s*include\s*<(.*)>', remaining_lines[0])
                )

                if not include_match:
                    break

                _, *remaining_lines = remaining_lines

                meta_directive.include_file_path   = pathlib.Path(output_directory_path, include_match.groups()[0])
                meta_directive.include_line_number = total_lines - len(remaining_lines)



            # Try parsing for a meta-directive.

            meta_directive_found = False

            while remaining_lines:



                # See if the next line is part of a meta-directive's header.

                meta_match = re.match(
                    r'\s*#\s*meta\b\s*(.*)' if source_file_path.suffix == '.py' else
                    r'\s*/\*\s*#\s*meta\b\s*(.*)',
                    remaining_lines[0]
                )

                if not meta_match:
                    break

                remaining_lines = remaining_lines[1:]

                if not meta_directive_found:
                    meta_directive_found                    = True
                    meta_directive.first_header_line_number = total_lines - len(remaining_lines)



                # Parse the meta-directive's header line.

                match meta_match.groups()[0].strip().split(maxsplit = 1):



                    # Meta-directive header line with a list of identifiers.

                    case [kind, *identifiers] if kind in (KINDS := ('export', 'import', 'global')):

                        identifiers, = identifiers or ['']
                        identifiers  = [
                            types.SimpleNamespace(
                                kind        = kind,
                                name        = identifier.strip(),
                                line_number = total_lines - len(remaining_lines),
                            )
                            for identifier in identifiers.split(',')
                            if identifier.strip()
                        ]



                        # Ensure there's actually any identifiers.

                        if not identifiers:

                            logger.error(
                                f'At least one identifier needs to be listed after {repr(kind)}.',
                                extra = {
                                    'frames' : (
                                        types.SimpleNamespace(
                                            source_file_path = source_file_path,
                                            line_number      = total_lines - len(remaining_lines),
                                        ),
                                    ),
                                },
                            )

                            raise MetaPreprocessorError



                        # Ensure each identifier look like an actual identifier.

                        if bad := next((
                            identifier
                            for identifier in identifiers
                            if not identifier.name.isidentifier()
                        ), None):

                            logger.error(
                                f'Failed to parse {repr(bad.name)} as an identifier.',
                                extra = {
                                    'frames' : (
                                        types.SimpleNamespace(
                                            source_file_path = source_file_path,
                                            line_number      = total_lines - len(remaining_lines),
                                        ),
                                    ),
                                },
                            )

                            raise MetaPreprocessorError



                        # Ensure each identifier look like an actual identifier.

                        if bad := next((
                            identifier
                            for identifier in identifiers
                            if identifier.name == 'Meta'
                        ), None):

                            logger.error(
                                f'Identifier name {repr(bad.name)} cannot be used.',
                                extra = {
                                    'frames' : (
                                        types.SimpleNamespace(
                                            source_file_path = source_file_path,
                                            line_number      = total_lines - len(remaining_lines),
                                        ),
                                    ),
                                },
                            )

                            raise MetaPreprocessorError



                        meta_directive.identifiers += identifiers



                    # Empty meta-directive header line;
                    # typically to just denote the start of a meta-directive.

                    case []:
                        pass



                    case _:

                        logger.error(
                            f'Unknown meta-header kind {repr(kind)}; must be one of: {repr(KINDS)}.',
                            extra = {
                                'frames' : (
                                    types.SimpleNamespace(
                                        source_file_path = source_file_path,
                                        line_number      = total_lines - len(remaining_lines),
                                    ),
                                ),
                            },
                        )

                        raise MetaPreprocessorError



            if not meta_directive_found:
                remaining_lines = remaining_lines[1:]
                continue



            # We now get the body of the meta-directive.

            meta_directive.body_line_number = total_lines - len(remaining_lines) + 1
            meta_directive.body_lines       = []

            if source_file_path.suffix == '.py':

                meta_directive.body_lines = remaining_lines
                remaining_lines           = []

            else:

                while True:

                    if not remaining_lines:

                        logger.error(
                            f'Meta-directive body not terminated with "*/"; reached end of file.',
                            extra = {
                                'frames' : (
                                    types.SimpleNamespace(
                                        source_file_path = source_file_path,
                                        line_number      = meta_directive.first_header_line_number,
                                    ),
                                ),
                            },
                        )

                        raise MetaPreprocessorError

                    body_line, *remaining_lines = remaining_lines

                    ending = '*/' in body_line

                    if ending:
                        body_line = body_line[:body_line.index('*/')]

                    meta_directive.body_lines += [body_line]

                    if ending:
                        break

                meta_directive.body_lines = deindent(
                    '\n'.join(meta_directive.body_lines),
                    multilined_string_literal = False,
                    single_line_comment       = '#'
                ).splitlines()



            # Ensure all identifiers listed are unique.

            for name, conflicts in coalesce(
                (identifier.name, identifier)
                for identifier in meta_directive.identifiers
            ):

                if len(conflicts) <= 1:
                    continue

                logger.error(
                    f'Identifier {repr(name)} should not be listed multiple times.',
                    extra = {
                        'frames' : tuple({
                            conflict.line_number : types.SimpleNamespace(
                                source_file_path = source_file_path,
                                line_number      = conflict.line_number,
                            )
                            for conflict in conflicts
                        }.values())
                    },
                )

                raise MetaPreprocessorError



            meta_directives += [meta_directive]



    # Ensure each meta-directive's include file path is unique.

    for include_file_path, conflicts in coalesce(
        (meta_directive.include_file_path, meta_directive)
        for meta_directive in meta_directives
        if meta_directive.include_file_path is not None
    ):

        if len(conflicts) <= 1:
            continue

        logger.error(
            f'Multiple meta-directives use the include file path {repr(include_file_path.as_posix())}.',
            extra = {
                'frames' : [
                    types.SimpleNamespace(
                        source_file_path = conflict.source_file_path,
                        line_number      = conflict.include_line_number,
                    )
                    for conflict in conflicts
                ]
            },
        )

        raise MetaPreprocessorError



    # Ensure each meta-directive's exported and global identifiers are unique.

    for name, conflicts in coalesce(
        (identifier.name, (identifier, meta_directive))
        for meta_directive in meta_directives
        for identifier     in meta_directive.identifiers
        if identifier.kind in ('export', 'global')
    ):

        if len(conflicts) <= 1:
            continue

        logger.error(
            f'Multiple meta-directives cannot define the same identifier {repr(name)}.',
            extra = {
                'frames' : [
                    types.SimpleNamespace(
                        source_file_path = conflict_meta_directive.source_file_path,
                        line_number      = conflict_identifier.line_number,
                    )
                    for conflict_identifier, conflict_meta_directive in conflicts
                ]
            },
        )

        raise MetaPreprocessorError



    # Ensure each meta-directive import from an actual existing identifier.

    all_defined_identifier_names = [
        identifier.name
        for meta_directive in meta_directives
        for identifier     in meta_directive.identifiers
        if identifier.kind in ('export', 'global')
    ]

    for meta_directive in meta_directives:

        for identifier in meta_directive.identifiers:

            if (
                identifier.kind == 'import' and
                identifier.name not in all_defined_identifier_names
            ):

                logger.error(
                    did_you_mean(
                        'Importing identifier {}, but no meta-directive exports that.',
                        identifier.name,
                        all_defined_identifier_names
                    ),
                    extra = {
                        'frames' : (
                            types.SimpleNamespace(
                                source_file_path = meta_directive.source_file_path,
                                line_number      = identifier.line_number,
                            ),
                        )
                    },
                )

                raise MetaPreprocessorError



    # Meta-directives with a bare header will implicitly import everything.

    for meta_directive in meta_directives:

        if any(
            identifier.kind in ('export', 'import', 'global')
            for identifier in meta_directive.identifiers
        ):
            continue

        meta_directive.identifiers += [
            types.SimpleNamespace(
                kind = 'implicit',
                name = name,
            )
            for name in all_defined_identifier_names
            if name not in (identifier.name for identifier in meta_directive.identifiers)
        ]



    # Meta-directives with global identifiers will have those identifiers be
    # implicitly imported into every other meta-directive without a global list.

    all_global_identifier_names = [
        identifier.name
        for meta_directive in meta_directives
        for identifier     in meta_directive.identifiers
        if identifier.kind == 'global'
    ]

    for meta_directive in meta_directives:

        if any(
            identifier.kind == 'global'
            for identifier in meta_directive.identifiers
        ):
            continue

        meta_directive.identifiers += [
            types.SimpleNamespace(
                kind = 'implicit',
                name = name,
            )
            for name in all_global_identifier_names
            if name not in (identifier.name for identifier in meta_directive.identifiers)
        ]



    # Sort the meta-directives.

    remaining_meta_directives  = meta_directives
    meta_directives            = []
    available_identifier_names = []

    while remaining_meta_directives:

        for meta_directive_i, meta_directive in enumerate(remaining_meta_directives):



            # See if all of the meta-directive's dependencies are satisfied.

            if not all(
                identifier.name in available_identifier_names
                for identifier in meta_directive.identifiers
                if identifier.kind in ('import', 'implicit')
            ):
                continue



            # All of the meta-directive's dependencies are satisfied,
            # so it can be evaluated at this point and have all of its
            # defined identifiers be added to the set.

            available_identifier_names += [
                identifier.name
                for identifier in meta_directive.identifiers
                if identifier.kind in ('export', 'global')
            ]



            # Acknowledge the meta-directive as processed.

            meta_directives += [meta_directive]
            del remaining_meta_directives[meta_directive_i]
            break



        # There's likely some sort of circular dependency.

        else:

            logger.error(
                f'Could not determine the next meta-directive to evaluate; '
                f'there may be a circular dependency.',
                extra = {
                    'frames' : [
                        types.SimpleNamespace(
                            source_file_path = meta_directive.source_file_path,
                            line_number      = meta_directive.first_header_line_number,
                        )
                        for meta_directive in remaining_meta_directives
                        if any(identifier.kind != 'implicit' for identifier in meta_directive.identifiers)
                    ]
                },
            )

            raise MetaPreprocessorError



    # Create the top-level main function that'll
    # evaluate all of the meta-directives.

    meta_main_lines = []

    meta_main_lines += deindent(
        '''
                def __META_MAIN_FUNCTION__(__META_DIRECTIVE_DECORATOR__):
                    pass

        '''
    ).splitlines()



    # Create the meta-directive functions.

    for meta_directive_i, meta_directive in enumerate(meta_directives):



        # List all of the identifiers that the meta-directive will depend upon.

        parameters = [
            'Meta',
            *[
                identifier.name
                for identifier in meta_directive.identifiers
                if identifier.kind in ('import', 'implicit')
            ]
        ]



        # List all of the identifiers that the
        # meta-directive will define the value of.
        # We have the dummy identifier `_` in case
        # there's no identifier to be defined by the
        # meta-directive.

        identifiers_to_be_defined = ['_'] + [
            identifier.name
            for identifier in meta_directive.identifiers
            if identifier.kind in ('export', 'global')
        ]



        # Make the meta-directive function that'll be executed by the decorator.

        meta_main_lines += deindent(
            f'''
                    @__META_DIRECTIVE_DECORATOR__({meta_directive_i})
                    def __META_DIRECTIVE_FUNCTION__({', '.join(parameters)}):

                        global {', '.join(identifiers_to_be_defined)}

            '''
        , indent = ' ' * 4).splitlines()



        # Insert the code for the meta-directive.

        meta_directive.meta_main_line_number = len(meta_main_lines) + 1

        meta_main_lines += deindent(
            '\n'.join(meta_directive.body_lines) + '\n',
            indent = ' ' * 8,
        ).splitlines()



    # Output the Python script of all meta-directives.
    # This is purely for debugging and diagnostics.

    meta_main_content = '\n'.join(meta_main_lines) + '\n'

    meta_main_file_path = pathlib.Path(output_directory_path, '__META_MAIN__.py')

    meta_main_file_path.parent.mkdir(parents = True, exist_ok = True)

    meta_main_file_path.write_text(meta_main_content)



    # Parse each meta-directive individually
    # to catch any syntax errors.

    for meta_directive in meta_directives:

        try:

            compile(
                '\n'.join(meta_directive.body_lines),
                filename = (filename := '__META_DIRECTIVE_PARSE__'),
                mode     = 'exec',
                flags    = ast.PyCF_ONLY_AST,
            )

        except SyntaxError as error:

            if error.filename != filename:
                raise

            logger.error(
                f'Syntax error: {repr(error.msg)}.',
                extra = {
                    'frames' : (
                        types.SimpleNamespace(
                            source_file_path = meta_directive.source_file_path,
                            line_number      = meta_directive.body_line_number + error.lineno - 1,
                        ),
                    )
                },
            )

            raise MetaPreprocessorError from error



    # Helper class that makes code generation easy and look nice.

    class Meta:

        output         = ''
        indent         = 0
        within_macro   = False
        overloads      = {}
        section_stack  = []



        # Helper routine to output lines.

        def line(*args):



            if Meta.section_stack:
                text               = Meta.section_stack[ -1]
                Meta.section_stack = Meta.section_stack[:-1]
                Meta.line(text)



            if not args: # Create single empty line for `Meta.line()`.
                args = ['''
                ''']



            for arg in args:

                match arg:
                    case str() : strings = [arg]
                    case _     : strings = list(arg)

                for string in strings:

                    for line in deindent(string).splitlines():



                        # Reindent.

                        line = ' ' * 4 * Meta.indent + line



                        # Escape newlines for multi-lined macros.

                        if Meta.within_macro:
                            line += '\\'



                        # No trailing spaces.

                        line = line.rstrip()



                        # Next line!

                        Meta.output += line + '\n'



        # Helper routine to handle scopes.

        @contextlib.contextmanager
        def enter(header = None, opening = None, closing = None, *, indented = None):



            # Determine the scope parameters.

            header_is = lambda *keywords: header is not None and re.search(fr'^\s*({'|'.join(keywords)})\b', header)

            if defining_macro := header_is('#define'):
                Meta.within_macro = True

            if   defining_macro                                         : suggestion = (None, None      , None)
            elif header_is('#if', '#ifdef', '#elif', '#else')           : suggestion = (None, '#endif'  , None)
            elif header_is('assert', 'static_assert', '_Static_assert') : suggestion = ('(' , ');'      , None)
            elif header_is('struct', 'union', 'enum')                   : suggestion = ('{' , '};'      , None)
            elif header_is('case')                                      : suggestion = ('{' , '} break;', None)
            elif header is not None and header.strip().endswith('=')    : suggestion = ('{' , '};'      , True)
            else                                                        : suggestion = ('{' , '}'       , None)

            if opening  is None: opening  = suggestion[0]
            if closing  is None: closing  = suggestion[1]
            if indented is None: indented = suggestion[2]



            # Header and opening lines.

            if header is not None:
                Meta.line(header)

            if indented:
                Meta.indent += 1

            if opening:
                Meta.line(opening)



            # Body.

            Meta.indent += 1
            yield
            Meta.indent -= 1



            # Closing lines.

            if closing is not None:
                Meta.line(closing)

            if indented:
                Meta.indent -= 1

            if defining_macro:
                Meta.within_macro = False
                Meta.line()



        # The actual routine to create the enumeration is a class so
        # that `Meta.enums` can be used as a context-manager if needed.

        def enums(*args, **kwargs):
            return Meta.__enums(*args, **kwargs)

        class __enums:



            # Whether or not we determine if `Meta.enums` is being used
            # as a context-manager is if the list of members is provided.

            def __init__(
                self,
                enum_name,
                enum_type,
                members = None,
                count   = 'constexpr'
            ):

                self.enum_name = enum_name
                self.enum_type = enum_type
                self.members   = members
                self.count     = count

                if self.members is not None:
                    self.__exit__()



            # By using a context-manager, the user can
            # create the list of enumeration members
            # with more complicated logic.

            def __enter__(self):

                if self.members is not None:
                    raise ValueError(
                        f'Cannot use `Meta.enums` as a context-manager '
                        f'when members are already provided.'
                    )

                self.members = []

                return self.members



            # Here we generate the output whether or
            # not a context-manager was actually used.

            def __exit__(self, *dont_care_about_exceptions):



                # By providing "enum_type", we can specify the width of the enumeration members;
                # this, however, is only supported in C++ and C23.
                # e.g: Meta.enums('Planet', 'u32', ...)   ->   enum Planet : u32 { ... }
                # e.g: Meta.enums('Planet', None , ...)   ->   enum Planet       { ... }

                if self.enum_type is None:
                    enum_type_suffix = ''
                else:
                    enum_type_suffix = f' : {self.enum_type}'



                # Format the list of members, some of which may be a name-value pair.

                self.members = list(self.members)

                for member_i, member in enumerate(self.members):

                    match member:
                        case (name, value) : value = c_repr(value)
                        case  name         : value = ...

                    self.members[member_i] = (f'{self.enum_name}_{c_repr(name)}', value)



                # Output the enumeration members with alignment.

                if self.members:

                    with Meta.enter(f'''
                        enum {self.enum_name}{enum_type_suffix}
                    '''):

                        for name, value, just_name in justify(
                            (
                                (None, name ),
                                (None, value),
                                ('<' , name ),
                            )
                            for name, value in self.members
                        ):
                            if value is ...:
                                Meta.line(f'{name},')
                            else:
                                Meta.line(f'{just_name} = {value},')



                # When there's no members, we have to forward-declare it,
                # because C doesn't allow empty enumerations.

                else:
                    Meta.line(f'enum {self.enum_name}{enum_type_suffix};')



                # Provide the amount of enumeration members that were defined;
                # this is useful for creating arrays and iterating with
                # for-loops and such.

                match self.count:



                    # Don't emit the count.

                    case None:
                        pass



                    # Use a macro, but this will have the disadvantage of
                    # not being scoped and might result in a name conflict.
                    # Most of the time, enumerations are defined at the global
                    # level, so this wouldn't matter, but enumerations can
                    # also be declared within a function; if so, then another
                    # enumeration of the same name cannot be declared later
                    # or else there'll be multiple #defines with different values.

                    case 'define':
                        Meta.define(f'{self.enum_name}_COUNT', len(self.members))



                    # Use a separate, anonymous enumeration definition to make the count.
                    # Unlike "define", this will be scoped, so it won't suffer the same
                    # issue of name conflicts. However, the compiler could emit warnings
                    # if comparisons are made between the enumeration members and this
                    # member count, because they are from different enumeration groups.

                    case 'enum':
                        Meta.line(f'''
                            enum{enum_type_suffix} {{ {self.enum_name}_COUNT = {len(self.members)} }};
                        ''')



                    # Use a constexpr declaration to declare the member count.
                    # Unlike "enum", the type of the constant is the same type
                    # as the underlying type of the enumeration, so the compiler
                    # shouldn't warn about comparisons between the two.
                    # This approach, however, relies on C23 or C++.

                    case 'constexpr':
                        Meta.line(f'''
                            static constexpr {self.enum_type} {self.enum_name}_COUNT = {len(self.members)};
                        ''')



                    # Unknown member-count style.

                    case unknown:
                        raise ValueError(f'Unknown member-count style of {repr(unknown)}.')



        # Helper routine to create C macro definitions.

        def define(*args, do_while = False, **overloading):



            # Parse syntax of the call.

            match args:



                case (name, expansion):
                    parameters = None



                case (name, (*parameters,), expansion):
                    pass



                case (name, parameter, expansion):
                    if parameter is None:
                        parameters = None
                    else:
                        parameters = [parameter]



                # Unknown syntax.

                case unknown:
                    raise ValueError(
                        f'Not sure what to do with the '
                        f'set of arguments: {repr(args)}.'
                    )



            # Macros can be "overloaded" by doing
            # concatenation of a preprocessor-time value.

            if overloading:



                # To C values.

                overloading = { key : c_repr(value) for key, value in overloading.items() }



                # Some coherency checks.

                if differences := [overload for overload in overloading if overload not in parameters]:
                    raise ValueError(
                        f'Overloaded argument "{differences[0]}" not in macro\'s parameter-list.'
                    )

                if name in Meta.overloads and Meta.overloads[name] != (parameters, tuple(overloading.keys())):
                    raise ValueError(
                        f'This overloaded macro instance has a different parameter-list from others.'
                    )



                # Make note of the fact that there'll be multiple instances of the "same macro".

                if name not in Meta.overloads:
                    Meta.overloads[name] = (parameters, tuple(overloading.keys()))



                # The name and parameters of this single macro instance itself.

                name       = f'__MACRO_OVERLOAD__{name}__{'__'.join(map(str, overloading.values()))}'
                parameters = [parameter for parameter in parameters if parameter not in overloading] or None



            # Determine the prototype of the macro.

            if parameters is None:
                prototype = f'{name}'
            else:
                prototype = f'{name}({', '.join(parameters)})'



            # Format the macro's expansion.

            expansion = deindent(c_repr(expansion))



            # Output macro that will multiple lines.

            if '\n' in expansion:

                with Meta.enter(f'#define {prototype}'):

                    if do_while:
                        with Meta.enter('do', '{', '}\nwhile (false)'):
                            Meta.line(expansion)

                    else:
                        Meta.line(expansion)



            # Just output a single-line macro wrapped in do-while.

            elif do_while:
                Meta.line(f'#define {prototype} do {{ {expansion} }} while (false)')



            # Just output an unwrapped single-line macro.

            else:
                Meta.line(f'#define {prototype} {expansion}')



        # Helper routine to create look-up tables.

        def lut(*arguments):



            # Parse the argument format.

            match arguments:



                # The type for the table is provided.

                case (table_type, table_name, table_rows):
                    pass



                # The type for the table will be created automatically.

                case (table_name, table_rows):

                    table_type = None



                case unknown:
                    raise ValueError(f'Unknown set of arguments: {repr(unknown)}.')



            # Make each table row have an index, or have it be `None` if not provided.

            table_rows = list(list(row) for row in table_rows)

            for row_i, row in enumerate(table_rows):
                if row and (isinstance(row[0], tuple) or isinstance(row[0], list)):
                    table_rows[row_i] = [None, *row]



            # Determine the type of each member.

            for table_row_i, (row_indexing, *members) in enumerate(table_rows):

                for member_i, member in enumerate(members):

                    match member:



                        # The type of each member is explicitly given.

                        case [member_type, member_name, member_value]:

                            if table_type is not None:
                                raise ValueError(
                                    f'Member type shouldn\'t be given when '
                                    f'the table type is already provided.'
                                )



                        # The type of each member is not given either because
                        # it's not needed or it'll be inferred automatically.

                        case [member_name, member_value]:

                            member_type = None



                        case unknown:
                            raise ValueError(f'Unknown row member format: {repr(unknown)}.')



                    members[member_i] = [member_type, member_name, c_repr(member_value)]



                table_rows[table_row_i] = [row_indexing, members]



            # Determine the table type.

            if table_type is None:

                match table_rows:



                    # This is just how we're going to handle empty tables.

                    case []:

                        table_type = 'struct {}'



                    # Create the type for the table.

                    case [[first_row_indexing, first_row_members], *rest]:

                        table_type = f'struct {{ {' '.join(
                            [
                                f'{member_type if member_type is not None else f'typeof({member_value})'} {member_name};'
                                for member_type, member_name, member_value in first_row_members
                            ] if table_rows else []
                        )} }}'



                    case unknown:
                        assert False, unknown



            # Generate the table with nice, aligned columns.

            with Meta.enter(f'static const {table_type} {table_name}[] ='):

                for just_row_indexing, *just_fields in justify(
                    (
                        ('<', f'[{row_indexing}] = ' if row_indexing is not None else ''),
                        *(
                            ('<', f'.{member_name} = {member_value}')
                            for member_type, member_name, member_value in members
                        ),
                    )
                    for row_indexing, members in table_rows
                ):
                    Meta.line(f'{just_row_indexing}{{ {', '.join(just_fields)} }},')



        # Helper routine to create a section header if any code was generated.

        @contextlib.contextmanager
        def section(text):

            original_depth      = len(Meta.section_stack)
            Meta.section_stack += [text]

            yield

            Meta.section_stack = Meta.section_stack[:original_depth]



    # Decorator to handle the initialization and
    # results of executing a meta-directive.

    defined_identifiers = {}

    def __META_DIRECTIVE_DECORATOR__(meta_directive_i):

        def decorator(function):

            meta_directive = meta_directives[meta_directive_i]

            nonlocal defined_identifiers



            # List the identifiers that the meta-directive will depend upon.

            parameters = { 'Meta' : Meta } | {
                identifier.name : defined_identifiers[identifier.name]
                for identifier in meta_directive.identifiers
                if identifier.kind in ('import', 'implicit')
            }



            # Evaluate the meta-directive code.

            function_globals = {}

            Meta.meta_directive = meta_directive
            Meta.output         = ''
            Meta.indent         = 0
            Meta.within_macro   = False
            Meta.overloads      = {}
            Meta.section_stack  = []



            # Start of the callback.

            if callback is None:

                callback_iterator = None

            else:

                callback_iterator = callback(meta_directives, meta_directive_i)

                if not isinstance(callback_iterator, types.GeneratorType):
                    raise RuntimeError('Meta-directive callback must be a generator.')

                try:
                    next(callback_iterator)
                except StopIteration:
                    raise RuntimeError('Meta-directive callback did not yield.')



            # Evaluate the meta-directive where the function's
            # global namespace will be inspected later on.

            try:

                types.FunctionType(function.__code__, function_globals)(**parameters)



            # Handle any run-time errors due to the meta-directive.

            except Exception as error:



                # Look at the stack frames from when
                # we began to evaluate the meta-directive.

                traces = traceback.extract_tb(sys.exc_info()[2])

                while traces and traces[0].name != '__META_DIRECTIVE_FUNCTION__':
                    del traces[0]



                # For each layer of the stack leading to the line that
                # caused the exception, we determine the file and line number.

                frames = []

                for trace in traces:



                    # The traceback is in one of the meta-directives, so
                    # we determine the corresponding meta-directive
                    # and calculate the offending line number.

                    if trace.filename == '__META_MAIN_FILE__':

                        (body_line_index, meta_directive), *_ = sorted(
                            (trace.lineno - meta_directive.meta_main_line_number, meta_directive)
                            for meta_directive in meta_directives
                            if trace.lineno >= meta_directive.meta_main_line_number
                        )

                        frames += [types.SimpleNamespace(
                            source_file_path = meta_directive.source_file_path,
                            line_number      = meta_directive.body_line_number + body_line_index + 1
                        )]



                    # The meta-directive at some point invoked `eval` or `exec`.
                    # There's not much we can do here to provide useful stack information.

                    elif trace.filename == '<string>':

                        pass



                    # The traceback is in some other Python file,
                    # so we just grab that.

                    else:

                        frames += [types.SimpleNamespace(
                            source_file_path = pathlib.Path(trace.filename).relative_to(pathlib.Path.cwd(), walk_up = True),
                            line_number      = trace.lineno
                        )]



                # Provide the nice diagnostic to show
                # the stack frames leading to the exception.

                logger.error(
                    f'Exception {repr(error.__class__.__name__)} raised: {repr(str(error))}.',
                    extra = {
                        'frames' : frames
                    },
                )

                raise MetaPreprocessorError from error



            # End of callback.

            if callback is not None:

                try:
                    next(callback_iterator)
                    stopped = False
                except StopIteration:
                    stopped = True

                if not stopped:
                    raise RuntimeError('Meta-directive callback did not return.')



            # If the meta-directive generates code, we output that code now.

            if Meta.meta_directive.include_file_path is not None:



                # We need to insert some stuff at the beginning of the file...

                generated   = Meta.output
                Meta.output = ''



                # Create the master macro for any overloaded macros.
                # This has to be done first because the overloaded macros
                # could be used later in the generated file after they're defined,
                # and if we don't have the master macro to have the overloaded
                # macros be invoked, errors will happen! We could also make the
                # master macro when we're making the first overloaded macro instance,
                # but this master macro could be inside of a #if, making it
                # potentially unexpectedly undefined in certain situations.

                if Meta.overloads:

                    for macro, (parameters, overloading) in Meta.overloads.items():

                        argument_list = [parameter for parameter in parameters if parameter not in overloading]

                        if argument_list : argument_list = f'({', '.join(argument_list)})'
                        else             : argument_list = ''



                        # Output the master macro.

                        Meta.define(
                            f'{macro}({', '.join(parameters)})',
                            f'__MACRO_OVERLOAD__{macro}__##{'##'.join(overloading)}{argument_list}'
                        )



                # Put back the rest of the code that was generated.

                if generated:
                    Meta.line(generated)



                # Spit out the generated code.

                pathlib.Path(Meta.meta_directive.include_file_path).parent.mkdir(parents = True, exist_ok = True)
                pathlib.Path(Meta.meta_directive.include_file_path).write_text(Meta.output)



            # Ensure all identifiers that are to be defined
            # by the meta-directive are actually defined.

            if undefined_identifiers := [
                identifier
                for identifier in meta_directive.identifiers
                if identifier.kind in ('export', 'global')
                if identifier.name not in function_globals
            ]:

                logger.error(
                    f'Missing definition for {repr(undefined_identifiers[0].name)}.',
                    extra = {
                        'frames' : (
                            types.SimpleNamespace(
                                source_file_path = meta_directive.source_file_path,
                                line_number      = undefined_identifiers[0].line_number,
                            ),
                        )
                    },
                )

                raise MetaPreprocessorError



            # Record the new values for the identifiers
            # that the meta-directive defined.

            defined_identifiers |= function_globals



        return decorator



    # Begin evaluating the meta-directives.

    meta_main_globals = {}

    exec(compile(meta_main_content, '__META_MAIN_FILE__', 'exec'), {}, meta_main_globals)

    meta_main_globals['__META_MAIN_FUNCTION__'](__META_DIRECTIVE_DECORATOR__)



    # Log the performance of the meta-preprocessor.

    if callback == default_callback:

        logger.debug(
            f'Meta-preprocessing {len(meta_directive_deltas)} meta-directives took {elapsed :.3f}s.',
            extra = {
                'table' : [
                    (location, f'{delta :.3f}s | {delta / elapsed * 100 : 5.1f}%')
                    for location, delta in sorted(meta_directive_deltas, key = lambda x: -x[1])
                ]
            }
        )



################################################################################
#
# S-expression parser.
#



# The default value mapper.

class Unquoted(str):
    pass

def default_mapping(value, quote):



    # Some direct substituations.

    match value:
        case 'False' : return False
        case 'True'  : return True
        case 'None'  : return None



    # Attempting to parse as an integer.

    try:
        return int(value)
    except ValueError:
        pass



    # Attempting to parse as a float.

    try:
        return float(value)
    except ValueError:
        pass



    # Symbols that are quoted with backticks are to be evaluated literally.
    # e.g:
    # >
    # >    (a b `2 + 2` c d)
    # >    (a b    4    c d)
    # >

    if quote == '`':
        return eval(value[1:-1], {}, {})



    # Other quoted symbols will just be a Python string.

    if quote:
        return value[1:-1]



    # We indicate that the symbol was unquoted.

    return Unquoted(value)



# The parser itself.

def parse_sexp(input, mapping = default_mapping):



    # Strip whitespace and single-line comments.

    line_number = 1

    def eat_filler():

        nonlocal input, line_number

        while True:



            # Reached end of input.

            if not input:
                break



            # Keep track of current line number.

            if input[0] == '\n':
                line_number += 1



            # Strip whitespace.

            if input[0] in string.whitespace:
                input = input[1:]



            # Strip single-line comment.

            elif input[0] == '#':
                input        = '\n'.join(input.split('\n', maxsplit = 1)[1:])
                line_number += 1



            # We're at the next token!

            else:
                break



    # Recursively parse the S-expression.

    def eat_expr():

        nonlocal input, line_number



        # Look for the start of the next token.

        eat_filler()

        if not input:
            raise SyntaxError('Reached end of input while looking for the next token.')



        # Parse subexpression.

        if input[0] == '(':

            input = input[1:]



            # Get each element.

            values = []

            while True:

                eat_filler()

                if input and input[0] == ')':
                    break
                else:
                    values += [eat_expr()]



            # Found the end of the subexpression.

            input = input[1:]

            return tuple(values)



        # Parse symbol.

        else:

            value             = ''
            quote             = None # TODO Escaping.
            parentheses_depth = 0

            while True:



                # At the end of the input or line.

                if not input or input[0] == '\n':

                    if quote is not None:
                        raise SyntaxError(f'On line {line_number}, string is missing ending quote ({quote}).')

                    break



                # Found end of the unquoted symbol.

                if input[0] in (string.whitespace + '#') and quote is None:
                    break



                # Determine if we found the opening/closing quotation.

                found_end_quote = input[0] == quote and value != ''

                if input[0] in ('"', "'", '`') and value == '':
                    quote = input[0]



                # For something like `(a b c unconnected-(ABC))`,
                # it'll be interpreted as: `('a', 'b', 'c', 'unconnected-(ABC)')`
                #
                # but for `(a b c unconnected)`,
                # it'll be interpreted as: `('a', 'b', 'c', 'unconnected')`.
                #
                # So we have to keep track of the parentheses-depth to know
                # whether or not we should consider `(` and `)` the end of
                # the token.

                if quote is None:

                    if input[0] == '(':

                        parentheses_depth += 1

                    elif input[0] == ')':

                        if parentheses_depth >= 1:

                            parentheses_depth -= 1

                        else:

                            break



                # Eat the next character for the symbol.

                value += input[0]
                input  = input[1:]



                # End of symbol if we found the ending quote.

                if found_end_quote:

                    # This is mostly to catch weird quote mismatches.
                    if input and input[0] not in string.whitespace + ')':
                        raise SyntaxError(
                            f'On line {line_number}, string should have whitespace or ")" after the ending quote ({quote}).'
                        )

                    break



            # Map the value if possible.

            assert value

            return mapping(value, quote)



    # Parse the input which should just be a single subexpression.

    eat_filler()

    if not input or input[0] != '(':
        raise SyntaxError(f'Input should start with the "(" token.')

    result = eat_expr()

    eat_filler()

    if input:
        raise SyntaxError(f'On line {line_number}, additional tokens were found; input should just be a single value.')

    return result



################################################################################
#
# Citation checker.
#



def process_citations(
    *,
    file_paths,
    reference_text_to_find     = None,
    replacement_reference_text = None,
    logger                     = pxd_logger
):



    if replacement_reference_text is not None and reference_text_to_find is None:
        logger.error(f'Cannot replace references without first providing the original reference.')
        sys.exit(1)



    # We'll be keeping track of any issues we find.

    issues = []

    def push_issue(citations, reason):

        nonlocal issues

        issues += [types.SimpleNamespace(
            citations = tuple(citations),
            reason    = reason,
        )]



    # Find all citations.

    all_citations = []

    for file_path in file_paths:



        # Skip any potential binary files.

        try:
            file_lines = file_path.read_text().splitlines()
        except UnicodeDecodeError:
            continue



        # Citations will be parsed as best as we can,
        # but issues can arise and will be recorded.

        def parse_citation(file_line_i, file_line, start_index):

            nonlocal all_citations, issues

            text = file_line[start_index:].removeprefix('@/')

            citation = types.SimpleNamespace(
                file_path         = file_path,
                line_number       = file_line_i + 1,
                whole_start_index = start_index,
                whole_end_index   = len(file_line),
                file_line         = file_line,
                attributes        = {
                    'pg'  : None,
                    'sec' : None,
                    'fig' : None,
                    'tbl' : None,
                },
                reference_type        = None,
                reference_text        = None,
                reference_start_index = None,
                reference_end_index   = None,
            )



            # Find attributes.

            for attribute in citation.attributes:

                if re.match(f'{attribute}\\b', text):

                    value, *text = text.split('/', maxsplit = 1)

                    if not text:
                        push_issue(
                            [citation],
                            f"Expected '/' at some point after attribute {repr(attribute)}, "
                            f"but reached end of line."
                        )
                        return

                    text, = text
                    value = value.removeprefix(attribute).strip()

                    citation.attributes[attribute] = value



            # Get reference prefix.

            for type in (
                'url',
            ):
                if text.startswith(prefix := f'{type}:'):
                    text                    = text.removeprefix(prefix)
                    citation.reference_type = type
                    break



            # Get the reference.

            if not text.startswith('`'):
                push_issue(
                    [citation],
                    f"Expected opening '`' for the citation's reference."
                )
                return

            text = text.removeprefix('`')

            citation.reference_start_index = len(file_line) - len(text)
            citation.reference_text, *text = text.split('`', maxsplit = 1)

            if not text:
                push_issue(
                    [citation],
                    f"Expected closing '`' for the citation's reference."
                )
                return

            text, = text

            citation.reference_end_index = citation.reference_start_index + len(citation.reference_text)
            citation.reference_text      = citation.reference_text.strip()



            # Determine if it's a basic citation reference definition.

            if text.lstrip().startswith(':'):

                text = text.lstrip().removeprefix(':')

                if citation.reference_type is not None:
                    push_issue(
                        [citation],
                        f"Citation cannot be of type {repr(citation.reference_type)} "
                        f"but also a reference definition (i.e. has postfix ':')."
                    )
                    return

                citation.reference_type = ':'



            citation.whole_end_index = len(file_line) - len(text)



            # Check page number.

            if citation.attributes['pg'] is not None:

                valid = False

                try:
                    page_number = int(citation.attributes['pg'])
                    valid       = page_number >= 1
                except ValueError:
                    pass

                if not valid:
                    push_issue(
                        [citation],
                        f"Citation's page number of {repr(citation.attributes['pg'])} "
                        f"might be a typo."
                    )



            # Check table and section.

            for attribute in ('tbl', 'sec'):

                value = citation.attributes[attribute]

                if value is not None and not (
                    len(value) >= 1
                    and value[ 0] in string.ascii_lowercase + string.ascii_uppercase + string.digits
                    and value[-1] in string.ascii_lowercase + string.ascii_uppercase + string.digits
                    and all(
                        character in string.ascii_lowercase + string.ascii_uppercase + string.digits + '.-'
                        for character in value
                    )
                ):
                    push_issue(
                        [citation],
                        f"Citation's {repr(attribute)} attribute of {repr(value)} "
                        f"might be a typo."
                    )



            # Ensure the reference is not empty.

            if not citation.reference_text:
                push_issue(
                    [citation],
                    f"Citation's reference is empty."
                )



            all_citations += [citation]



        for file_line_i, file_line in enumerate(file_lines):
            for matching in re.finditer('@/', file_line):
                parse_citation(file_line_i, file_line, matching.start())



    # Organize the citations.

    citations_by_reference = coalesce(
        (citation.reference_text, citation)
        for citation in sorted(
            all_citations,
            key = lambda citation: (
                citation.reference_type == 'url'
            )
        )
    )



    # Find additional issues between citations.

    for citation_reference_text, citations in citations_by_reference:



        # Ensure citations of URL references are used consistently.

        if any(
            citation.reference_type == 'url'
            for citation in citations
        ):

            if not all(
                citation.reference_type == 'url'
                for citation in citations
            ):
                push_issue(
                    citations,
                    f'URL reference {repr(citation_reference_text)} not used consistently.'
                )

            continue



        # Ensure definitions aren't missing or duplicated.

        match [
            citation
            for citation in citations
            if citation.reference_type == ':'
        ]:

            case []:
                push_issue(
                    citations,
                    f'Missing definition for reference {repr(citation_reference_text)}.'
                )

            case [citation_definition]:
                pass

            case citation_definitions:
                push_issue(
                    citation_definitions,
                    f'Conflicting definitions for reference {repr(citation_reference_text)}.'
                )



        # Ensure no stale sources.

        if not any(
            citation.reference_type is None
            for citation in citations
        ):
            push_issue(
                citations,
                f'Source reference defined but never used.'
            )



    # Display the table of all citations found.

    def format_citation(just_file_path, just_line_number, citation, coloring, *, color_reference = False):

        if color_reference:
            start_index = citation.reference_start_index
            end_index   = citation.reference_end_index
        else:
            start_index = citation.whole_start_index
            end_index   = citation.whole_end_index

        return '[{} : {}]    {}'.format(
            just_file_path,
            just_line_number,
            (
                f'{citation.file_line[:start_index]}'
                f'{coloring}'
                f'{citation.file_line[start_index : end_index]}'
                f'{ANSI_RESET}'
                f'{citation.file_line[end_index:]}'
            ).strip(),
        )

    citation_table_output = ''

    for citation, just_file_path, just_line_number in justify(
        (
            (None, citation                     ),
            ('<' , citation.file_path.as_posix()),
            ('<' , citation.line_number         ),
        )
        for citation_reference_text, citations in citations_by_reference
        for citation in sorted(
            citations,
            key = lambda citation: (
                citation.reference_type is None
            )
        )
        if reference_text_to_find is None or citation_reference_text == reference_text_to_find
    ):
        citation_table_output += format_citation(
            just_file_path,
            just_line_number,
            citation,
            (
                {
                    'url' : f'{ANSI_BG_CYAN}{ANSI_FG_BLACK}',
                    ':'   : f'{ANSI_BG_GREEN}{ANSI_FG_BLACK}',
                    None  : f'{ANSI_FG_GREEN}',
                }[citation.reference_type]
                if reference_text_to_find is None else
                ANSI_BG_MAGENTA
            ),
            color_reference = reference_text_to_find is not None
        ) + '\n'

    if citation_table_output:
        logger.info(citation_table_output)



    # Report basic statistics.

    relevant_citation_count = sum(
        reference_text_to_find is None or citation.reference_text == reference_text_to_find
        for citation in all_citations
    )

    if reference_text_to_find is None:

        logger.info('Found {} citations and {} unique references.'.format(
            relevant_citation_count,
            len(citations_by_reference),
        ))

    elif relevant_citation_count:

        logger.info('Found {} citations with reference of {}.'.format(
            relevant_citation_count,
            repr(reference_text_to_find)
        ))

    else:

        logger.info(did_you_mean(
            'No citation has reference of {}.',
            reference_text_to_find,
            dict(citations_by_reference).keys(),
        ))



    # Report any issues.

    for issue in issues:

        context = ''

        for citation, just_file_path, just_line_number in justify(
            (
                (None, citation                     ),
                ('<' , citation.file_path.as_posix()),
                ('<' , citation.line_number         ),
            )
            for citation in issue.citations
        ):
            context += format_citation(
                just_file_path,
                just_line_number,
                citation,
                f'{ANSI_BG_YELLOW}{ANSI_FG_BLACK}',
            ) + '\n'

        logger.warning(
            f'{issue.reason}' '\n'
            f'{context}'
        )



    # Determine if we should do reference replacement.

    if replacement_reference_text is None:
        return

    if not relevant_citation_count:
        logger.warning('No citation to do replacement with.')
        return

    if replacement_reference_text in dict(citations_by_reference):
        logger.warning(f'Reference {repr(replacement_reference_text)} already exists.')

    logger.warning(
        f"Enter 'yes' to replace the {repr(reference_text_to_find)} with {repr(replacement_reference_text)}; "
        f"otherwise abort."
    )

    try:
        response = input()
    except KeyboardInterrupt:
        response = None

    if response != 'yes':
        logger.error(f'Aborted the renaming.')
        return



    # Replace all matching citations with a new reference.

    for file_path, citations in coalesce(
        (citation.file_path, citation)
        for citation in all_citations
        if citation.reference_text == reference_text_to_find
    ):

        # Being aware of line-ending convention.

        file_lines = file_path.read_text().splitlines(keepends = True)



        # References are replaced in a line going from right-to-left
        # so multiple citations on the same line will work out.

        for citation in sorted(
            citations,
            key = lambda citation: (citation.line_number, -citation.reference_start_index)
        ):
            file_lines[citation.line_number - 1] = (
                file_lines[citation.line_number - 1][:citation.reference_start_index] +
                replacement_reference_text                                            +
                file_lines[citation.line_number - 1][citation.reference_end_index:]
            )



        # Update the file while preserving line-endings.

        file_path.write_text(''.join(file_lines))
