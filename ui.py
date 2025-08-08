import builtins, types, enum
from ..pxd.utils import is_a_subclass_of, did_you_mean, find_dupe, OrdSet
from ..pxd.log   import log, ANSI, Indent



class UI:



    # The UI object is used to easily define command-line interface commands in Python.
    # e.g:
    # >
    # >    def my_ui_hook(verb, parameters):
    # >        ...
    # >        yield
    # >        ...
    # >
    # >    my_ui = UI('MyUI', 'This is the description of my UI.', my_ui_hook)
    # >
    # >    @my_ui(...)
    # >    def my_first_verb(parameters):
    # >        ...
    # >
    # >    @my_ui(...)
    # >    def my_second_verb(parameters):
    # >        ...
    # >

    def __init__(self, name, description, verb_hook = None):

        self.name        = name
        self.description = description
        self.verb_hook   = verb_hook
        self.verbs       = {}



        # By default, we create a help verb to show all the other verbs the user defines for this UI.

        @self(
            {
                'description' : f'Show usage of "{self.name}"; use "{self.name} help all" to show more detailed information.',
            },
            {
                'name'        : 'verb',
                'description' : 'The verb to show more detailed information on, or "all" to show everything.',
                'type'        : str,
                'default'     : None,
            },
        )
        def help(parameters, show_header = None, hide_help = False):



            # If a specific verb was given, see if it exists.

            if parameters.verb not in (None, 'all') and parameters.verb not in self.verbs:

                help(types.SimpleNamespace(verb = None))

                with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                    log()
                    log(f'No verb by the name of "{parameters.verb}" found; see the list of verbs above.')
                    did_you_mean(parameters.verb, self.verbs.keys())



            # Show information about this UI.

            if show_header is None:
                show_header = parameters.verb in (None, 'all')

            if show_header:

                log(ANSI(f'> {self.name} [verb] (parameters...)', 'bold', 'underline'))
                log(self.description)



            # Explain each verb.
            # We sort to put the "help" verb last so it'd be the first thing the user sees
            # near the cursor of the shell.

            with Indent(' ' * (4 if show_header else 0)):

                for verb in sorted(self.verbs.values(), key = lambda verb: verb.name == 'help'):



                    # Show only the needed verbs.

                    if parameters.verb not in (None, 'all') and verb.name != parameters.verb:
                        continue

                    if hide_help and verb.name == 'help':
                        continue



                    # Explain the verb and show its parameter-list.

                    if parameters.verb in (None, 'all'):
                        log()

                    parts = ['>', self.name, verb.name]

                    if isinstance(verb, UI):
                        parts += ['[subverb]', '(subparameters...)']
                    else:
                        parts += [parameter_schema.representation for parameter_schema in verb.parameter_schemas]

                    log(ANSI(' '.join(parts), 'bold', 'underline'))
                    log(verb.description)



                    # Show additional information but only if we don't overwhelm the user.

                    if parameters.verb is None:
                        continue



                    # For UI verbs, we rely on the sub-UI's help.

                    if isinstance(verb, UI):

                        with Indent():
                            verb.invoke(['help', 'all'], show_header = False, hide_help = True)

                        continue



                    # Show information on the verb's parameters.

                    with Indent():
                        for parameter_schema in verb.parameter_schemas:



                            # Explain the parameter.

                            log()
                            log(f'{parameter_schema.representation} {parameter_schema.description}')



                            with Indent():



                                # Show the parameter's default value.

                                if parameter_schema.default is not ...:
                                    log(f'= {parameter_schema.default}')



                                # List the available options, if applicable.

                                if UI.__is_option_type(options := parameter_schema.type):

                                    for option in options:

                                        if is_a_subclass_of(option, enum.Enum):
                                            option = option.name

                                        log(f'- {option}')



        # Allow other parts of the code to be able to invoke the help verb directly.

        self.help = help



    # This is where we register new verbs for the UI.

    def __call__(self, *arguments):

        match arguments:



            # Nesting another UI inside of a UI.
            # e.g:
            # >
            # >    parent_ui(sub_ui)
            # >


            case [sub_ui] if isinstance(sub_ui, UI):

                if sub_ui.name in self.verbs:
                    raise RuntimeError(f'Verb by the name of "{sub_ui.name}" defined more than once.')

                self.verbs[sub_ui.name] = sub_ui



            # Making a new verb for the UI through a decorator.
            # e.g:
            # >
            # >    @my_ui(...)
            # >    def my_verb(parameters):
            # >        ...
            # >

            case _:

                verb_schema, *parameter_schemas = arguments

                parameter_schemas = list(parameter_schemas)

                def decorator(function):



                    # Parse the verb's schema.

                    verb_name       = verb_schema.pop('name', function.__name__)
                    verb_decription = verb_schema.pop('description')

                    if verb_schema:
                        raise RuntimeError(f'Leftover verb schema: {verb_schema}.')



                    # The parameter schemas will determine how the verb will be invoked.

                    for parameter_schema_i, parameter_schema in enumerate(parameter_schemas):



                        # Parse the parameter's schema.

                        parameter_schemas[parameter_schema_i] = types.SimpleNamespace(
                            identifier     = parameter_schema.pop('name'),
                            description    = parameter_schema.pop('description'),
                            type           = parameter_schema.pop('type'),
                            default        = parameter_schema.pop('default', ...),
                        )

                        parameter_schemas[parameter_schema_i].flag = parameter_schema.pop(
                            'flag',
                            parameter_schemas[parameter_schema_i].type == bool # This is what you'd want most of the time.
                        )

                        if parameter_schema:
                            raise RuntimeError(f'Leftover parameter schema: {parameter_schema}.')

                        parameter_schema = parameter_schemas[parameter_schema_i]



                        # Ensure that when we use SimpleNamespace that all of the parameters are accessible.

                        if not parameter_schema.identifier.isidentifier():
                            raise RuntimeError(f'Parameter name "{parameter_schema.identifier}" is not a valid identifier.')



                        # Determine the user-friendly representation of the parameter.

                        parameter_schema.representation = parameter_schema.identifier.replace('_', '-')

                        if parameter_schema.flag:
                            parameter_schema.representation = f'--{parameter_schema.representation}'

                        if parameter_schema.default is ...:
                            parameter_schema.representation = f'*{parameter_schema.representation}'

                        parameter_schema.representation = f'({parameter_schema.representation})'



                    if dupe := find_dupe(parameter_schema.identifier for parameter_schema in parameter_schemas):
                        raise RuntimeError(f'Parameter name "{dupe}" used more than once.')



                    # Save the verb into the collection.

                    if verb_name in self.verbs:
                        raise RuntimeError(f'Verb by the name of "{verb_name}" defined more than once.')

                    self.verbs[verb_name] = types.SimpleNamespace(
                        name              = verb_name,
                        description       = verb_decription,
                        parameter_schemas = parameter_schemas,
                        function          = function,
                    )



                    return function

                return decorator



    # Once all UI verbs have been defined,
    # the UI can be invoked and it'll automatically handle parsing the provided arguments.

    def invoke(self, arguments, *bypass_args, **bypass_kwargs):



        # If no arguments, then we just provide the help information.

        if not arguments:
            arguments = ['help']



        # Find the verb.

        verb_name, *arguments = arguments

        if verb_name not in self.verbs:

            self.help(types.SimpleNamespace(verb = None))

            with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                log()
                log(f'No verb by the name of "{verb_name}" found; see the list of verbs above.')
                did_you_mean(verb_name, self.verbs.keys())

            return 1

        verb = self.verbs[verb_name]



        # If the verb is another UI, then we hand off execution to it.

        if isinstance(verb, UI):
            return self.__execute(lambda: verb.invoke(arguments, *bypass_args, **bypass_kwargs), verb, None)



        # We first gather all of the arguments that are flags.
        # e.g:
        # >
        # >    MyUI "hello" "world" --output="This" 123 --silent
        # >                         ^^^^^^^^^^^^^^^     ^^^^^^^^
        # >

        flag_arguments    = {}
        nonflag_arguments = []

        for argument in arguments:



            # We process non-flag arguments later on.

            if not argument.startswith(prefix := '--'):
                nonflag_arguments += [argument]
                continue



            # Grab the RHS of the flag if there is one.
            # e.g:
            # >
            # >    MyUI "hello" "world" --output="This" 123 --silent
            # >                                  ^^^^^^
            # >

            flag_name, *flag_value = argument.removeprefix(prefix).split('=')

            if flag_value == []:
                flag_value = None
            else:
                flag_value, = flag_value



            # Make sure the flag argument is unique.

            if flag_name in flag_arguments:

                self.help(types.SimpleNamespace(verb = verb_name))

                with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                    log()
                    log(f'Flag "--{flag_name}" given more than once.')

                return 1

            flag_arguments[flag_name] = flag_value



        # We now handle the flag arguments.

        parameters = {}

        for flag_name, flag_value in flag_arguments.items():



            # Find the matching parameter to go with the flag.

            for parameter_schema in verb.parameter_schemas:

                if parameter_schema.identifier in parameters:
                    continue

                if parameter_schema.identifier.replace('_', '-') != flag_name:
                    continue

                if parameter_schema.type != bool and flag_value is None:

                    self.help(types.SimpleNamespace(verb = verb_name))

                    with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                        log()
                        log(
                            f'Parameter {parameter_schema.representation} is not a boolean flag and must be given a value; '
                            f'see the verb help above.'
                        )

                    return 1

                parameters[parameter_schema.identifier] = 'True' if flag_value is None else flag_value

                break



            # No parameter found to go with this flag.

            else:

                self.help(types.SimpleNamespace(verb = verb_name))

                with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                    log()
                    log(f'No parameter to match with flag "--{flag_name}"; see the verb help above.')
                    did_you_mean(
                        f'--{flag_name}',
                        (f'--{parameter_schema.identifier.replace('_', '-')}' for parameter_schema in verb.parameter_schemas)
                    )

                return 1



        # We now move onto handling the non-flag arguments.
        # e.g:
        # >
        # >    MyUI "hello" "world" --output="This" 123 --silent
        # >         ^^^^^^^ ^^^^^^^                 ^^^
        # >

        for argument in nonflag_arguments:



            # Find the first parameter that hasn't been done yet.

            for parameter_schema in verb.parameter_schemas:

                if parameter_schema.identifier in parameters:
                    continue

                if parameter_schema.flag:

                    self.help(types.SimpleNamespace(verb = verb_name))

                    with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                        log()
                        log(
                            f'Argument "{argument}" is assumed to be for parameter {parameter_schema.representation}, '
                            f'but this parameter must be a flag.'
                        )
                        log(f'Try (--{parameter_schema.identifier.replace('_', '-')}="{argument}") instead.')

                    return 1

                parameters[parameter_schema.identifier] = argument

                break



            # If all parameters have been accounted for, then we have been given an extraneous argument.

            else:

                self.help(types.SimpleNamespace(verb = verb_name))

                with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                    log()
                    log(f'No parameter to match with "{argument}"; see the verb help above.')

                return 1



        # Now we validate and parse each parameter.

        for parameter_schema in verb.parameter_schemas:

            if parameter_schema.identifier not in parameters:
                continue

            parameter_value = parameters[parameter_schema.identifier]

            match parameter_schema.type:



                # The argument should've been a string, which it always is, so not much to do here.

                case builtins.str:
                    pass



                # The argument should've been an integer.

                case builtins.int:
                    try:
                        parameter_value = int(parameter_value)
                    except ValueError:

                        self.help(types.SimpleNamespace(verb = verb_name))

                        with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                            log()
                            log(f'Parameter {parameter_schema.representation} needs to be an integer; got "{parameter_value}".')

                        return 1



                # The argument should've been a boolean, so we try to interpret it as so.

                case builtins.bool:

                    FALSY  = ('0', 'f', 'n', 'no' , 'false')
                    TRUTHY = ('1', 't', 'y', 'yes', 'true' )

                    if parameter_value.lower() in FALSY:
                        parameter_value = False

                    elif parameter_value.lower() in TRUTHY:
                        parameter_value = True

                    else:

                        self.help(types.SimpleNamespace(verb = verb_name))

                        with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                            log()
                            log(f'Parameter {parameter_schema.representation} needs to be a boolean; got "{parameter_value}".')
                            log(f'Truthy values are {', '.join(f'"{x}"' for x in TRUTHY if x)}.')
                            log(f'Falsy  values are {', '.join(f'"{x}"' for x in FALSY      )}.')
                            log(f'Values are case-insensitive.')

                        return 1



                # The argument should've been one of many options.

                case options if UI.__is_option_type(options):

                    if is_a_subclass_of(options, enum.Enum):
                        options = { option.name : option for option in options }

                    if parameter_value not in options:

                        self.help(types.SimpleNamespace(verb = verb_name))

                        with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                            log()
                            log(
                                f'Value "{parameter_value}" is not a valid option for {parameter_schema.representation}; '
                                f'see the options above.'
                            )
                            did_you_mean(parameter_value, options)

                        return 1

                    if isinstance(options, dict):
                        parameter_value = options[parameter_value]



                # This parameter's type hasn't been handled yet.

                case unsupported:
                    raise RuntimeError(f'Unsupported parameter type: {unsupported}.')



            # Update the parameter with the parsed value.

            parameters[parameter_schema.identifier] = parameter_value



        # Now we assign parameters with their default value if it hasn't been accounted for yet.
        # We need to do this after we parsed and validated the parameters so that we can have
        # default values that can be outside the parameter's specified type (e.g. parameter of
        # type `int` can have default value of `None`).

        for parameter_schema in verb.parameter_schemas:

            if parameter_schema.identifier in parameters:
                continue

            if parameter_schema.default is ...:

                self.help(types.SimpleNamespace(verb = verb_name))

                with ANSI('fg_red'), Indent('[ERROR] ', hanging = True):
                    log()
                    log(f'Missing required parameter {parameter_schema.representation}; see the verb help above.')

                return 1

            parameters[parameter_schema.identifier] = parameter_schema.default

        parameters = types.SimpleNamespace(**parameters)



        return self.__execute(lambda: verb.function(parameters, *bypass_args, **bypass_kwargs), verb, parameters)



    # Helper routine for determining whether or not a parameter should be interpreted as set of options.

    def __is_option_type(type):
        match type:
            case list() | tuple() | set() | OrdSet() | dict()            : return True
            case enumeration if is_a_subclass_of(enumeration, enum.Enum) : return True
            case _                                                       : return False



    # Routine to execute a verb alongside with the hook.

    def __execute(self, function, verb, parameters):



        # Begin the hook.

        if self.verb_hook:

            iterator = self.verb_hook(verb, parameters)

            if not isinstance(iterator, types.GeneratorType):
                raise RuntimeError(f'Verb hook for "{self.name}" must be a generator.')

            try:
                next(iterator)
            except StopIteration as error:
                raise RuntimeError(f'Verb hook for "{self.name}" did not yield.') from error

        else:
            iterator = None



        # Execute!

        exit_code = function()



        # End the hook.

        if self.verb_hook:

            stopped = False

            try:
                next(iterator)
            except StopIteration:
                stopped = True

            if not stopped:
                raise RuntimeError(f'Verb hook for "{self.name}" did not return.')



        return exit_code
