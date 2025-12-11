import types, difflib, sys



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

    def __init__(self, *, name, description, logger):

        self.name        = name
        self.description = description
        self.verbs       = []
        self.logger      = logger
        self.new_verb(
            {
                'name'        : ...,
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

                for parameter_schema in verb.parameter_schemas:

                    output += f'        {parameter_schema.formatted_name} {parameter_schema.description}' '\n'



                    # Show that the parameter is optional if applicable.

                    if parameter_schema.has_default:

                        match parameter_schema.default:

                            case str() | int() | float() | bool():
                                default = repr(parameter_schema.default)

                            case _: # Not easily representable.
                                default = '(optional)'

                        output += f'        = {default}' '\n'



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

            verb_name        = properties_of_verb.pop('name')
            verb_description = properties_of_verb.pop('description')

            if verb_name is ...:
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
                    description     = parameter_description,
                    type            = parameter_type,
                    has_default     = parameter_has_default,
                    default         = parameter_default,
                )]



            # Register the new verb.

            self.verbs += [types.SimpleNamespace(
                name              = verb_name,
                description       = verb_description,
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



        # TODO.

        parameters = {}



        # TODO.

        remaining_parameter_schemas = verb.parameter_schemas[:]

        while remaining_parameter_schemas:



            # Find an argument that could be matched up
            # with the next parameter schema in line.

            for argument_i, argument in enumerate(remaining_arguments):
                break
            else:
                break



            # TODO.

            parameters[remaining_parameter_schemas[0].identifier_name] = remaining_arguments[argument_i]

            del remaining_parameter_schemas[0]
            del remaining_arguments[argument_i]



        # TODO.

        for parameter_schema in remaining_parameter_schemas:

            if parameter_schema.has_default:

                parameters[parameter_schema.identifier_name] = parameter_schema.default



            # Missing required parameter.

            else:

                self.help(types.SimpleNamespace(
                    verb_name = verb.name,
                ))

                self.logger.error(f'Missing parameter {parameter_schema.formatted_name}.')

                sys.exit(1)



        # There shouldn't be any leftover arguments.

        if remaining_arguments:

            self.help(types.SimpleNamespace(
                verb_name = verb.name,
            ))

            self.logger.error(f'Extra argument {repr(remaining_arguments[0])}.')

            sys.exit(1)



        verb.function(types.SimpleNamespace(**parameters))
