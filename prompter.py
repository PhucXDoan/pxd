import types



class Interface:



    # Interfaces are where all verbs are
    # grouped together and are eventually invoked.

    def __init__(self, name, logger):

        self.name   = name
        self.verbs  = []
        self.logger = logger



        # Create the default help verb.

        @self.new_verb(
            {
                'name'        : ...,
                'description' : f'Show detailed usage of {repr(self.name)}.'
            },
        )
        def help(parameters):

            self.logger.info('meow!')



    # Routine for registering new verbs to the interface.

    def new_verb(self, properties_of_verb, *properties_of_parameters):

        def decorator(function):



            # Process verb properties.

            verb_name        = properties_of_verb.pop('name')
            verb_description = properties_of_verb.pop('description')

            if verb_name is ...:
                verb_name = function.__name__

            if properties_of_verb:
                raise ValueError(
                    f'Leftover verb properties: {repr(properties_of_verb)}.'
                )

            if any(verb_name == past_verb.name for past_verb in self.verbs):
                raise ValueError(
                    f'Verb name {repr(verb_name)} already used.'
                )



            # Process parameter properties.

            schema_of_parameters = []

            for parameter_property in properties_of_parameters:

                parameter_name        = parameter_property.pop('name')
                parameter_description = parameter_property.pop('description')
                parameter_type        = parameter_property.pop('type')

                if parameter_property:
                    raise ValueError(
                        f'Leftover parameter properties: {repr(parameter_property)}.'
                    )

                schema_of_parameters += [types.SimpleNamespace(
                    name        = parameter_name,
                    description = parameter_description,
                    type        = parameter_type,
                )]



            # Register the new verb.

            self.verbs += [types.SimpleNamespace(
                name                 = verb_name,
                description          = verb_description,
                schema_of_parameters = schema_of_parameters,
                function             = function,
            )]

            return function

        return decorator



    # Given some arguments, call onto the
    # appropriate verb with the parsed parameters.

    def invoke(self, given):



        # TODO.

        if not given:
            raise NotImplementedError



        # TODO.

        given_verb_name, *given_arguments = given

        for verb in self.verbs:
            if verb.name == given_verb_name:
                break
        else:
            raise NotImplementedError


        # TODO.

        parameters = None


        # TODO.

        for parameter_schema in verb.schema_of_parameters:

            for argument_i, argument in enumerate(given_arguments):
                pass



        verb.function(parameters)
