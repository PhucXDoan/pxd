#!/usr/bin/env python3
import builtins, os, sys, datetime, copy, types, traceback, contextlib, collections, re, enum

################################################################ Meta Primitives ################################################################

class MetaError(Exception):
	pass

class Meta:

	def Collect(fs):

		def decorator(f):
			nonlocal fs
			match fs:
				case list():
					fs += [f]
				case dict():
					assert f.__name__ not in fs, 'Function named `{f.__name__}` already in the collection.'
					fs[f.__name__] = f
			return f

		return decorator

	class Obj:

		def __init__(self, dct=None, **fields):
			assert dct is None or not fields, \
				'Meta.Obj has both an argument and kwargs; likely a mistake?'
			for key, value in (fields if dct is None else dct).items():
				self.__dict__[key] = value

		def __getattr__(self, key):
			assert key in ('__deepcopy__', '__setstate__'), \
				f'The Meta.Obj has no field (.{key}) to read.'
			raise AttributeError

		def __setattr__(self, key, value):
			assert key in self.__dict__, \
				f'The Meta.Obj has no field (.{key}) to write.'
			self.__dict__[key] = value

		def __getitem__(self, key):
			assert key in self.__dict__, \
				f'The Meta.Obj has no field [`{key}`] to read.'
			return self.__dict__[key]

		def __setitem__(self, key, value):
			assert key in self.__dict__, \
				f'The Meta.Obj has no field [`{key}`] to write.'
			self.__dict__[key] = value
			return value

		def __iter__(self):
			for name, value in self.__dict__.items():
				yield (name, value)

		def __repr__(self):
			return f'Meta.Obj({ ', '.join(f'{k} = {v}' for k, v in self) })'

		def __contains__(self, key):
			return key in self.__dict__

	class AddOn:

		def __init__(self, dct=None, **fields):
			assert dct is None or not fields, \
				'Meta.AddOn has both an argument and kwargs; likely a mistake?'
			for key, value in (fields if dct is None else dct).items():
				self.__dict__[key] = value

		def __getattr__(self, key):
			assert key in ('__deepcopy__', '__setstate__'), \
				f'The Meta.AddOn has no field (.{key}) to read.'
			raise AttributeError

		def __setattr__(self, key, value):
			assert key not in self.__dict__, \
				f'The Meta.AddOn has field (.{key}) already.'
			self.__dict__[key] = value

		def __getitem__(self, key):
			assert key in self.__dict__, \
				f'The Meta.AddOn has no field [`{key}`] to read.'
			return self.__dict__[key]

		def __setitem__(self, key, value):
			assert key not in self.__dict__, \
				f'The Meta.AddOn has field [`{key}`] already.'
			self.__dict__[key] = value
			return value

		def __iter__(self):
			for name, value in self.__dict__.items():
				yield (name, value)

		def __repr__(self):
			return f'Meta.AddOn({ ', '.join(f'{k} = {v}' for k, v in self) })'

		def __contains__(self, key):
			return key in self.__dict__

	def Table(header, *entries):

		for entry in Meta.exam(entries, lambda entry: entry is not None and not isinstance(entry, tuple)):
			assert False, f'The Meta.Table has a non-tuple row: {entry}.'

		for entry in Meta.exam(entries, lambda entry: len(entry) != len(header)):
			assert False, \
				f'The Meta.Table has {len(header)} columns ({', '.join(header)}), ' \
				f'but this entry has {len(entry)}: {entry}.'

		table = []

		for entry in entries:
			if entry is not None: # Allows for an entry to be easily omitted.
				table += [Meta.Obj(**dict(zip(header, entry)))]

		return table

	def Dict(items):

		items = list(items)

		for key, _ in Meta.exam((value, key) for key, value in items):
			assert False, f'The Meta.Dict has conflicting keys for `{key}`.'

		return { key : value for key, value in items }

	def stringify(x):
		match x:
			case bool()  : return str(x).lower()
			case float() : return str(int(x) if x.is_integer() else x)
			case _       : return str(x)

	def exam(values, predicate=None):

		# If no predicate, check if `values` have any overlapping values.
		if predicate is None:

			match values:
				case dict() : pairs = values.items()
				case _      : pairs = values

			history = collections.defaultdict(lambda: [])

			for person, birthday in pairs:
				history[birthday] += [person]

			for birthday, people in history.items():
				if len(people) >= 2:
					yield birthday, people

		# Otherwise, find a value that satisfies the predicate.
		else:
			for value in values:
				if predicate(value):
					yield value

	def line(string='\n\n'):

		# Split to process each line in order to do indenting correctly for multilined input strings.
		lines = (string + '\n').splitlines()

		# Remove first empty line; useful for multilined strings.
		if lines and lines[0].strip() == '':
			lines = lines[1:]

		# Remove last empty line; useful for multilined strings.
		if lines and lines[-1].strip() == '':
			lines = lines[:-1]

		global_indent = None
		for line in lines:

			# Determine line's indent level.
			line_indent = len(line) - len(line.lstrip('\t'))

			# Determine the whole string's indent level based on the first line with actual text.
			if global_indent is None and line.strip():
				global_indent = line_indent

			# Set indents appropriately.
			line         = line.removeprefix('\t' * min(line_indent, global_indent or 0))
			line         = '\t' * Meta.indent + line if line.strip() else ''
			Meta.string += line + (' \\' if Meta.within_macro else '') + '\n'

	def define(lhs, rhs, *, do_while=False):

		if isinstance(rhs, str) and '\n' in rhs:
			with Meta.enter(f'#define {lhs}'):
				if do_while:
					with Meta.enter('do', '{', '}\nwhile (false)'):
						Meta.line(rhs)
				else:
					Meta.line(rhs)
		else:
			expansion = Meta.stringify(rhs).strip()

			if do_while:
				Meta.line(f'#define {lhs} do {{ {expansion} }} while (false)')
			else:
				Meta.line(f'#define {lhs} {expansion}')

	def overload(macro_name, args, expansion):

		arg_names                           = [arg[0] if isinstance(arg, tuple) else arg for arg in args]
		determiner_names, determiner_values = zip(*[ arg for arg in args if     isinstance(arg, tuple)])
		nondeterminer_names                 =      [ arg for arg in args if not isinstance(arg, tuple)]
		overload                            = (arg_names, determiner_names, nondeterminer_names)

		if macro_name in Meta.overloads:
			assert Meta.overloads[macro_name] == overload
		else:
			Meta.overloads[macro_name] = overload

		Meta.define(f'_{macro_name}__{'__'.join(map(Meta.stringify, determiner_values))}({', '.join(nondeterminer_names)})', expansion)

	@contextlib.contextmanager
	def enter(header=None, opening=None, closing=None, *, indented=None):

		defining_macro = False

		# Automatically configure the opening and closing lines if possible.

		def match(*keywords):
			string = fr'^\s*({'|'.join(keywords)})\b'
			return header is not None and re.search(string, header)

		if match('#if', '#ifdef', '#elif', '#else'):
			if closing is None: closing = '#endif'

		elif match('struct', 'union', 'enum'):
			if opening is None: opening = '{'
			if closing is None: closing = '};'

		elif match('case'):
			if opening is None: opening  = '{'
			if closing is None: closing  = '} break;'

		elif match('#define'):
			defining_macro    = True
			Meta.within_macro = True

		else:
			if opening is None: opening = '{'
			if closing is None: closing = '}'

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

	def ifs        (cases): return Meta.__ifs(cases, elifs=False, has_else=False, pound_if=False)
	def IFS        (cases): return Meta.__ifs(cases, elifs=False, has_else=False, pound_if=True )
	def if_elses   (cases): return Meta.__ifs(cases, elifs=False, has_else=True , pound_if=False)
	def IF_ELSES   (cases): return Meta.__ifs(cases, elifs=False, has_else=True , pound_if=True )
	def elifs      (cases): return Meta.__ifs(cases, elifs=True , has_else=False, pound_if=False)
	def ELIFS      (cases): return Meta.__ifs(cases, elifs=True , has_else=False, pound_if=True )
	def elifs_else (cases): return Meta.__ifs(cases, elifs=True , has_else=True , pound_if=False)
	def ELIFS_ELSE (cases): return Meta.__ifs(cases, elifs=True , has_else=True , pound_if=True )
	def __ifs(cases, *, elifs, has_else, pound_if):

		match cases:
			case dict()     : items = list(cases.items())
			case Meta.Obj() : items = list(cases.__dict__.items())
			case _          : assert False

		for index, (condition, value) in enumerate(items):

			# Determine header.
			if index and elifs:
				if pound_if : header = f'#elif {condition}'
				else        : header = f'else if ({condition})'
			else:
				if pound_if : header = f'#if {condition}'
				else        : header = f'if ({condition})'

			# Suppress the default closing line if there's going to be another case.
			closing = '' if pound_if and ((elifs and index != len(items) - 1) or has_else) else None

			# Create the if-body.
			with Meta.enter(header, None, closing):
				yield (condition, value)

			# Create the else-body if needed.
			if not elifs and has_else:
				if items:
					if pound_if : header = f'#else'
					else        : header = f'else'
				else:
					header = None
				with Meta.enter(header):
					yield (None, value)

		# Create final else-body if needed.
		if elifs and has_else:
			if items:
				if pound_if : header = f'#else'
				else        : header = f'else'
			else:
				header = None
			with Meta.enter(header):
				yield (None, None)

	def enums(enum_name, underlying_type, members=None, *, counted=False): # TODO Can be made into a contextlib.

		if type(enum_name) == enum.EnumType:
			assert members is None
			members   = enum_name
			enum_name = enum_name.__name__

		if underlying_type is None:
			header = f'enum {enum_name}'
		else:
			header = f'enum {enum_name} : {underlying_type}'

		if not members and not counted:

			# An empty enumeration is ill-formed according to the C/C++ standard, so we'll have to forward-declare it.
			Meta.line(f'{header};')

		else:
			with Meta.enter(f'{header}'):

				# Determine the longest name.
				if type(members) == enum.EnumType:
					justification = max([0] + [len(member.name) for member in members])
				else:
					justification = max([0] + [len(member[0]) for member in members if isinstance(member, tuple)])

				for member in members:

					# From python enumeration.
					if type(members) == enum.EnumType:
						member_name, member_value = member.name, member.value

					# Enumeration with explicit value.
					elif isinstance(member, tuple):
						member_name, member_value = member

					# With implicit value.
					else:
						member_name, member_value = member, None

					if member_value is None:
						Meta.line(f'{enum_name}_{member_name},')
					else:
						if isinstance(member_value, bool):
							member_value = str(member_value).lower()
						Meta.line(f'{enum_name}_{member_name.ljust(justification)} = {member_value},')

				# Provide member count; it's a macro so it won't have to be explicitly handled in switch statements.
				if counted:
					Meta.define(f'{enum_name}_COUNT', len(members))

################################################################ Meta-Preprocessor ################################################################

def do(*, output_dir_path, source_file_paths, additional_context, quiet=False, noexec=False, output_receipt=True):

	meta_decls    = []
	meta_includes = []

	def location_of(a, b = None, *, line_offset=0):
		match (a, b):
			case (source_file_path, line_number) if isinstance(source_file_path, str) and isinstance(line_number, int):
				return f'[{source_file_path}:{line_number + line_offset}]'
			case (meta_directive, None):
				return location_of(meta_directive.source_file_path, meta_directive.line_number, line_offset=line_offset)

	def execute(directive, gbls):

		prepended_lines = []

		try:

			# We have to introduce a wrapper since `exec` assumes class definition context
			# and some weird non-intuitive variable binding stuff can happen.
			prepended_lines += ['def __META_MAIN__():']

			# In case there's no code.
			prepended_lines += ['\tpass']

			# Declare globals for the exports.
			if hasattr(directive, 'exports') and directive.exports:
				prepended_lines += [f'\tglobal {', '.join(directive.exports)}']

			# Execute.
			meta_code  = ''
			meta_code += '\n'.join(prepended_lines)
			meta_code += '\n'
			meta_code += '\n'.join(f'\t{line}' for line in directive.lines)
			meta_code += '\n'
			meta_code += '__META_MAIN__()\n'
			exec(meta_code, gbls, {})

		except Exception as err:

			err_trace = traceback.format_exc()

			match type(err):
				case builtins.SyntaxError      : err_lineno = err.lineno
				case builtins.IndentationError : err_lineno = err.lineno
				case _                         : err_lineno = [stack.lineno for stack in traceback.extract_tb(sys.exc_info()[2]) if stack.name == '__META_MAIN__'][0]

			match type(err):
				case builtins.SyntaxError    : err_detail = 'Syntax error!'
				case builtins.AssertionError : err_detail = err.args[0] if err.args else f'Assertion failed!'
				case _                       : err_detail = repr(err)

			diagnostic  = ''
			diagnostic += 128 * '#' + '\n'
			diagnostic += err_trace
			diagnostic += 128 * '#' + '\n'
			diagnostic += '\n'
			diagnostic += f'{location_of(directive, line_offset = err_lineno - len(prepended_lines))}: {err_detail}'
			raise MetaError(diagnostic)

	################################ Get Meta-Directives ################################

	for source_file_path in source_file_paths:

		remaining_lines       = open(source_file_path, 'rb').read().decode('UTF-8').splitlines()
		remaining_line_number = 1

		while remaining_lines:

			header_line            = remaining_lines[0]
			header_line_number     = remaining_line_number
			remaining_lines        = remaining_lines[1:]
			remaining_line_number += 1

			def eat_body_lines():

				nonlocal remaining_lines, remaining_line_number

				if remaining_lines[0].strip().startswith('/*'):

					body_lines    = []
					global_indent = None

					for body_line in [remaining_lines[0].strip().removeprefix('/*').strip(), *remaining_lines[1:]]:

						remaining_lines        = remaining_lines[1:]
						remaining_line_number += 1

						# Truncate up to the end of the block comment.
						if (ending := body_line.find('*/')) != -1:
							body_line = body_line[:ending]

						# Determine indent level.
						original_line_indent = len(body_line) - len(body_line.lstrip('\t'))

						# Determine global indent if needed and possible.
						a_comment = body_line.strip().startswith('#')
						nonempty  = body_line.strip() != ''
						if global_indent is None and len(body_lines) and nonempty and not a_comment:
							global_indent = original_line_indent

						# Cut away the extraneous indent. It's possible the the line has less
						# indentation than the global indentation, but we won't worry too much about that honestly.
						body_line = body_line.removeprefix('\t' * min(original_line_indent, global_indent or 0))

						# Got line!
						body_lines += [body_line]
						if ending != -1:
							break

					return body_lines

				else:
					return None

			#
			# Parse for a meta-decl.
			#

			tmp = header_line
			tmp = tmp.strip()

			if tmp.startswith('/*'): # Meta-decls are identified in comment blocks...
				tmp = tmp.removeprefix('/*')
				tmp = tmp.strip()

				if tmp.startswith('#meta'): # ... with a special tag.
					tmp = tmp.removeprefix('#meta')
					if (index := tmp.find('//')) != -1: tmp = tmp[:index]
					if (index := tmp.find('#' )) != -1: tmp = tmp[:index]
					tmp = tmp.strip()
					tmp = tmp.split(':')

					#
					# Process meta-decl header.
					#

					meta_decl = types.SimpleNamespace(
						source_file_path = source_file_path,
						line_number      = header_line_number,
						lines            = eat_body_lines(),
						exports          = [],
						imports          = [],
					)

					if meta_decl.lines is None:
						raise MetaError(f'{location_of(meta_decl)} Meta-decl is missing body.')

					def parse_for_symbols(string):

						symbols = []

						for symbol in [x.strip() for x in string.strip().split(',')]:
							if symbol in symbols:
								raise MetaError(f'{location_of(meta_decl)} Duplicate symbol "{symbol}" in meta-decl header.')
							elif symbol == '':
								pass # Likely means there's an extra comma; we'll just ignore it instead of being anal about it.
							else:
								symbols += [symbol]

						return symbols

					match tmp:
						case [exports_string]:
							meta_decl.exports = parse_for_symbols(exports_string)
							meta_decl.imports = []
						case [exports_string, imports_string]:
							meta_decl.exports = parse_for_symbols(exports_string)
							meta_decl.imports = parse_for_symbols(imports_string)
						case _:
							raise MetaError(f'{location_of(meta_decl)} Invalid arguments to meta-decl header.')

					#
					# Check for export collisions.
					#

					for symbol in meta_decl.exports:
						for conflict in meta_decls:
							if symbol in conflict.exports:
								raise MetaError(f'Two meta-decls export the same symbol "{symbol}": {location_of(meta_decl)} and {location_of(conflict)}.')

					meta_decls += [meta_decl]

			#
			# Parse for a meta-include.
			#

			tmp = header_line
			tmp = tmp.strip()

			if tmp.startswith('#include'): # Meta-includes are identified by preprocessor include directives...
				tmp = tmp.removeprefix('#include')
				tmp = tmp.strip()

				match tmp[0] if tmp else None:
					case '<': end_quote = '>'
					case '"': end_quote = '"'
					case _  : end_quote = None

				if end_quote is not None and (include_file_path_len := tmp[1:].find(end_quote)) != -1:
					if (include_file_path := tmp[1:][:include_file_path_len]).endswith('.meta'): # ... with a specific file extension.

						meta_include = types.SimpleNamespace(
							source_file_path = source_file_path,
							output_file_path = f'{output_dir_path}/{include_file_path}',
							line_number      = header_line_number,
							lines            = eat_body_lines(),
						)

						# Meta-includes are not required to have a body, so this allows the same generated code to be used multiple times.
						if meta_include.lines is not None:

							conflict = None

							for other in meta_includes:
								if other.output_file_path == meta_include.output_file_path:
									conflict = other
									break

							if conflict is None:
								meta_includes += [meta_include]
							else:
								raise MetaError(f'Conflicting meta-include for "{meta_include.output_file_path}": {location_of(meta_include)} and {location_of(conflict)}.')

	#
	# Check for missing exports.
	#

	for meta_decl in meta_decls:
		for symbol in meta_decl.imports:
			if not any(symbol in other.exports for other in meta_decls):
				raise MetaError(f'{location_of(meta_decl)} The meta-decl depends on "{symbol}" but no meta-decl exports it.')

	################################ Evaluate Meta-Decls ################################

	initial_context = copy.deepcopy(additional_context | { 'Meta' : Meta })
	full_context    = copy.deepcopy(initial_context)

	if tasks := [[False, meta_decl] for meta_decl in meta_decls]:

		if not quiet:
			if noexec:
				print("Meta-decls that would've been evaluated:")
			else:
				print('Meta-decls evaluated:')

		# Still got some meta-decl left to execute?
		while any(not executed for executed, meta_decl in tasks):

			deadend = True

			for task_index, (executed, meta_decl) in enumerate(tasks):

				# No need to evaluate the meta-decl again.
				if executed:
					continue

				# There's still some unsatisfied dependencies.
				if not all(symbol in full_context for symbol in meta_decl.imports):
					continue

				if not quiet:
					print(f'\t{location_of(meta_decl)} {', '.join(meta_decl.exports)}')

				# Skip evaluation.
				if noexec:
					continue

				# Execute meta-decl with the necessary context.
				tasks[task_index][0] = True
				deadend              = False
				gbls                 = copy.deepcopy(initial_context | { symbol : full_context[symbol] for symbol in meta_decl.imports })
				execute(meta_decl, gbls)

				# Process the execution's resulting global namespace.
				for gbl, value in gbls.items():

					# Ignore certain globals that were already a part of the context.
					if gbl == '__builtins__' or gbl in initial_context or gbl in meta_decl.imports:
						continue

					# Export global into the full context.
					if gbl in meta_decl.exports:
						full_context[gbl] = value

				# Ensure all exports were found.
				for symbol in meta_decl.exports:
					if symbol not in full_context:
						raise MetaError(f'{location_of(meta_decl)} Missing definition for exported symbol "{symbol}".')

			# No meta-decl managed to execute? Must be some sort of circular dependency!
			if not noexec and deadend:
				for executed, meta_decl in tasks:
					if unsatisfied_symbols := [f'"{symbol}"' for symbol in meta_decl.imports if symbol not in full_context]:
						raise MetaError(f'{location_of(meta_decl)} Unsatisfiable import encountered (likely due to circular dependencies): {', '.join(unsatisfied_symbols)}.')

			if noexec:
				break

	elif not quiet:
		print('No meta-decls found.')

	################################ Evaluate Meta-Includes ################################

	os.makedirs(output_dir_path, exist_ok=True) # Make output directory.

	if meta_includes:

		if not quiet:
			if noexec:
				print("Meta-includes that would've been evaluated:")
			else:
				print('Meta-includes evaluated:')

		for meta_include in meta_includes:

			if not quiet:
				print(f'\t{location_of(meta_include)} "{meta_include.output_file_path}"')

			# Skip evaluation.
			if noexec:
				continue

			# Execute.
			Meta.string       = ''
			Meta.indent       = 0
			Meta.overloads    = {}
			Meta.within_macro = False
			if not noexec:
				execute(meta_include, copy.deepcopy(full_context))

			# Format generated code.
			generated   = Meta.string
			Meta.string = ''

			# Some info about the generated code.
			if output_receipt:
				Meta.line(f'// {location_of(meta_include)} {datetime.datetime.now()}.')

			# Put any overloaded macros first.
			if Meta.overloads:
				if Meta.string:
					Meta.line()
				for macro_name, (arg_names, determiner_names, nondeterminer_names) in Meta.overloads.items():
					Meta.define(f'{macro_name}({', '.join(arg_names)})', f'_{macro_name}__##{'##'.join(determiner_names)}({', '.join(nondeterminer_names)})')

			# Insert rest of the code that was generated.
			if generated:
				if Meta.string:
					Meta.line()
				Meta.line(generated)

			# Save generated code.
			open(meta_include.output_file_path, 'w').write(Meta.string)

	elif not quiet:
		print('No meta-includes found.')
