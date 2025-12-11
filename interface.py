import types, difflib, sys, builtins



# TODO Factor out.

RESET       = '\x1B[0m'
BOLD        = '\x1B[1m'
UNDERLINE   = '\x1B[4m'
FG_BLACK    = '\x1B[30m'
FG_RED      = '\x1B[31m'
FG_GREEN    = '\x1B[32m'
FG_YELLOW   = '\x1B[33m'
FG_BLUE     = '\x1B[34m'
FG_MAGENTA  = '\x1B[35m'
FG_CYAN     = '\x1B[36m'
FG_WHITE    = '\x1B[37m'
BG_BLACK    = '\x1B[40m'
BG_RED      = '\x1B[41m'
BG_GREEN    = '\x1B[42m'
BG_YELLOW   = '\x1B[43m'
BG_BLUE     = '\x1B[44m'
BG_MAGENTA  = '\x1B[45m'
BG_CYAN     = '\x1B[46m'
BG_WHITE    = '\x1B[47m'



# TODO Maybe factor out.

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



class Interface:



    # Interfaces are where all verbs are
    # grouped together and are eventually invoked.

    def __init__(
        self,
        *,
        name,
        description,
        logger,
        hook = None,
    ):

        self.name        = name
        self.description = description
        self.verbs       = []
        self.logger      = logger
        self.hook        = hook
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

        output += f'> {UNDERLINE}{BOLD}{self.name} [verb] (parameters...){RESET}' '\n'
        output += f'{self.description}'                                           '\n'
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

            output += f'    > {UNDERLINE}{BOLD}{self.name} {FG_GREEN}{verb.name}{RESET}{UNDERLINE}{BOLD}'



            # Verb parameters in the invocation.

            for parameter_schema in verb.parameter_schemas:

                output += f' {parameter_schema.formatted_name}'

            output += f'{RESET}' '\n'



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
                        f'            {line}'
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
                parameter_has_default     = 'default' in parameter_property
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

    def invoke(self, given):



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

                    case list() | tuple():

                        if value not in parameter_schema.type:

                            self.logger.error(did_you_mean(
                                f'Parameter {parameter_schema.formatted_name} '
                                f'given invalid option of {{}}.',
                                value,
                                parameter_schema.type,
                            ))

                            sys.exit(1)

                    case dict():

                        if value not in parameter_schema.type:

                            self.logger.error(did_you_mean(
                                f'Parameter {parameter_schema.formatted_name} '
                                f'given invalid option of {{}}.',
                                value,
                                parameter_schema.type.keys(),
                            ))

                            sys.exit(1)

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
