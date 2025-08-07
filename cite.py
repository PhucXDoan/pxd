import re, sys, types, pathlib, string, collections, difflib
from ..pxd.ui    import UI
from ..pxd.log   import log, did_you_mean
from ..pxd.utils import *

CITATION_TAG = '@' '/' # Written like this so that the script won't accidentally think this is a citation.
ui           = UI('cite', 'Manage citations within the codebase.')


def get_file_paths():

    #
    # TODO We have dumb logic here to get something that sort of
    # resembles .gitignore. It's not very good, because apparently
    # there's no easy way to do recursive `**` globs that's built-in. Sigh.
    #

    citeignore_file_path = root(f'./.citeignore')

    if citeignore_file_path.is_file():

        citeignore_entries = [
            line.strip()
            for line in citeignore_file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]

    else:
        citeignore_entries = []

    def is_ignored(file_path):

        for pattern in citeignore_entries:
            if pattern.startswith('*.'):
                if file_path.match(pattern):
                    return True
            elif pattern.endswith('/'):
                if any(part == pattern.removesuffix('/') for part in file_path.parts):
                    return True
            else:
                assert False, f'Unsupported pattern: {pattern}'

        return False

    return [
        pathlib.Path(root, file_name)
        for root, dirs, file_names in root('./').walk()
        for file_name in file_names
        if not pathlib.Path(root, file_name).is_dir() and not is_ignored(pathlib.Path(root, file_name))
    ]



################################################################################################################################



def get_citations():

    citations = []
    issues    = []

    for file_path in get_file_paths():



        # Some stuff might be binary, so we'll skip over it when we can't read it properly.

        try:
            lines = file_path.read_text().splitlines()
        except UnicodeDecodeError:
            continue



        # Look for the magic citation tags and try the parse the citations.

        class ParsingIssue(Exception):
            pass

        for line_number, line, column in (
            (line_i + 1, line, match.start())
            for line_i, line in enumerate(lines)
            for match in re.finditer(CITATION_TAG, line)
        ):

            def report_issue(reason):
                nonlocal issues
                issues += [types.SimpleNamespace(
                    file_path   = file_path,
                    line_number = line_number,
                    reason      = reason,
                )]

            try:

                remainder = line[column + len(CITATION_TAG):]
                citation  = types.SimpleNamespace(
                    file_path   = file_path,
                    line_number = line_number,
                    column      = column,
                    line        = line,
                )



                # Get every citation field until we reach the source.
                # e.g:
                # >
                # >    (AT)/pg 123/sec abc/`The Bible`.
                # >         ^^^^^^ ^^^^^^^ ^
                # >

                citation.fields = {}

                while True:



                    # See if we've found the source.

                    for citation.source_usage in (None, 'by', 'url'):



                        # Determine how the source name will be used.
                        # Some sources are "inlined", that is, they don't have a source definition, like for instance URLs.
                        # Most citations reference a source that's not inlined however, so the source definition will be defined elsewhere.
                        # e.g:
                        # >
                        # >    (AT)/pg 123/sec abc/`The Bible`.
                        # >                        ^ Not inlined.
                        # >
                        # >    (AT)/pg 123/sec abc/by:`Phuc Doan`.
                        # >                        ^ Inlined.
                        # >
                        # >    (AT)/pg 123/sec abc/url:`www.google.com`.
                        # >                        ^ Inlined.
                        # >

                        if citation.source_usage is None:
                            prefix = '`'
                        else:
                            prefix = f'{citation.source_usage}:`'

                        if not remainder.startswith(prefix):
                            continue

                        remainder = remainder.removeprefix(prefix)



                        # Get the source name.
                        # e.g:
                        # >
                        # >    (AT)/pg 123/sec abc/url:`www.google.com`.
                        # >                             ^~~~~~~~~~~~~^
                        # >

                        start                            = len(line) - len(remainder)
                        citation.source_name, *remainder = remainder.split('`', 1)
                        end                              = start + len(citation.source_name)

                        if remainder == []:
                            raise ParsingIssue(f'Missing closing backtick (`) after source name.')

                        remainder, = remainder

                        citation.source_name         = citation.source_name.strip()
                        citation.source_name_columns = (start, end)

                        break

                    else:
                        citation.source_usage = ... # Haven't found the source yet.

                    if citation.source_usage is not ...:
                        break



                    # Find the end of the field.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >         ~~~~~~^
                    # >

                    field, *remainder = remainder.split('/', 1)

                    field = field.strip()

                    if not field:
                        raise ParsingIssue(f'Expected a field name.')

                    if remainder == []:
                        raise ParsingIssue(f'Expected a forward-slash (/).')

                    remainder, = remainder



                    # Get the field name and content.
                    # e.g:
                    # >
                    # >    (AT)/pg 123/sec abc/`The Bible`.
                    # >         ^^ ^^^
                    # >

                    field_name, *field_content = field.split(' ', 1)

                    if field_content == []:
                        raise ParsingIssue(f'Field "{field_name}" given no value.')

                    field_content, = field_content

                    if field_name in citation.fields:
                        raise ParsingIssue(f'Field "{field_name}" specified more than once.')

                    citation.fields[field_name] = field_content



                # We have now scanned through the entire citation.
                # e.g:
                # >
                # >    (AT)/by Phuc Doan/pg 13/sec abc/`The Bible`.
                # >    ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
                # >

                citation.text = line[column : len(line) - len(remainder)]



                # Validate each field.

                citation.listing = None

                for field_name, field_content in citation.fields.items():

                    match field_name:



                        # Get the page number.
                        # e.g:
                        # >
                        # >    (AT)/by Phuc Doan/pg 13/sec abc/`The Bible`.
                        # >                         ^^
                        # >

                        case 'pg':

                            if any(c in field_content for c in string.whitespace):
                                report_issue(
                                    f'Field "{field_name}" is "{field_content}" which has whitespace; '
                                    f'probably a mistake?'
                                )

                            elif not all(character in string.digits for character in field_content):
                                report_issue(
                                    f'Field "{field_name}" is "{field_content}" which has characters other than digits 0-9; '
                                    f'probably a mistake?'
                                )

                            elif field_content.startswith('0'):
                                report_issue(
                                    f'Field "{field_name}" is "{field_content}" which starts with digit 0; '
                                    f'probably a mistake?'
                                )



                        # Get the listing.
                        # e.g:
                        # >
                        # >    (AT)/by Phuc Doan/pg 13/sec abc/`The Bible`.
                        # >                                ^^^
                        # >

                        case 'tbl' | 'fig' | 'sec':

                            if citation.listing is not None:
                                report_issue(
                                    f'Fields "{citation.listing}" and "{field_name}" both given; '
                                    f'only at most one listing field is needed.'
                                )

                            else:

                                citation.listing = field_name

                                if not field_content.startswith(tuple(string.ascii_letters + string.digits)):
                                    report_issue(
                                        f'Field "{field_name}" is "{field_content}" which does not start with an alphanumeric character; '
                                        f'probably a mistake?'
                                    )

                                elif not field_content.endswith(tuple(string.ascii_letters + string.digits)):
                                    report_issue(
                                        f'The "{field_name}" field value is "{field_content}" which does not end with an alphanumeric character; '
                                        f'probably a mistake?'
                                    )

                                elif any(c in field_content for c in string.whitespace):
                                    report_issue(
                                        f'Field "{field_name}" is "{field_content}" which has whitespace; '
                                        f'probably a mistake?'
                                    )

                                elif not all(c in string.ascii_letters + string.digits + '.-' for c in field_content):
                                    report_issue(
                                        f'Field "{field_name}" is "{field_content}" which has a character typically not associated with listing codes; '
                                        f'probably a mistake?'
                                    )



                        # Unknown field.

                        case _:
                            report_issue(f'Field "{field_name}" is not supported.')



                # If a colon is next, then the citation is actually a source definition;
                # otherwise, it should be a reference to a source.
                # e.g:
                # >
                # >    The user guide states that we need to do X, Y, and Z. (AT)/`RSX`.
                # >                                                          ^^^^^^^^^^ Citation that's a reference.
                # >
                # >    (AT)/`RSX`: RockSat-X User Guide (August 31, 2023) (Rev-Draft).
                # >              ^ Citation that's a source definition.
                # >

                if remainder.strip().startswith(':'):

                    if citation.source_usage is not None:
                        raise ParsingIssue(f'Citation cannot have a "{citation.source_usage}" source and also be a source definition.')

                    citation.source_usage = 'definition'

                    if citation.fields:
                        report_issue(f'A source definition should not have fields.')

                elif citation.source_usage is None:
                    citation.source_usage = 'reference'



                citations += [citation]



            # Some sort of irrecoverable issue was encountered while parsing the citation...

            except ParsingIssue as error:
                report_issue(error.args[0])



    # Organize the citations by source names and then the usage of the source.
    # We also sort the citations so that it's trivial to print the citations out later on.

    database = collections.defaultdict(lambda: collections.defaultdict(lambda: []))

    def sorting(citation):

        try:
            pg = int(citation.fields.get('pg', 0))
        except ValueError:
            pg = 0

        return (
            citation.source_name,
            pg,
            citation.listing or '',
            citation.fields.get(citation.listing, ''),
            citation.file_path,
            citation.line_number
        )

    for citation in sorted(citations, key = sorting):
        database[citation.source_name][citation.source_usage] += [citation]



    # Find issues between citations.

    for source_name, source_usage_citations in database.items():

        match source_usage_citations:



            # Citation references a source that's not defined anywhere.

            case { 'reference' : references, **rest } if not rest:

                for reference in references:

                    issues += [types.SimpleNamespace(
                        file_path   = reference.file_path,
                        line_number = reference.line_number,
                        reason      = f'Undefined reference to source "{reference.source_name}".',
                    )]



            # A source that's defined multiple times.

            case { 'definition' : [first, *others] } if others:

                for other in others:
                    issues += [types.SimpleNamespace(
                        file_path   = other.file_path,
                        line_number = other.line_number,
                        reason      = f'Source "{other.source_name}" is already defined at [{first.file_path}:{first.line_number}]',
                    )]



            # A source that's not referenced by any citation.

            case { 'definition' : [definition], **rest } if not rest:

                issues += [types.SimpleNamespace(
                    file_path   = definition.file_path,
                    line_number = definition.line_number,
                    reason      = f'Source "{definition.source_name}" never used',
                )]



            # A source with a single definition and some citations that reference it.

            case { 'definition': [definition], 'reference': references, **rest } if not rest:

                pass # No issues with this.



            # A source with conflicting usages.
            # e.g:
            # >
            # >    (AT)/by:`google.com`.    <- Is "google.com" an author, a URL, or a source that's defined elsewhere?
            # >    (AT)/url:`google.com`.   <- "
            # >    (AT)/`google.com`.       <- "
            # >

            case _ if len(source_usage_citations) >= 2:

                for source_usage, source_citations in source_usage_citations.items():
                    for citation in source_citations:
                        issues += [types.SimpleNamespace(
                            file_path   = citation.file_path,
                            line_number = citation.line_number,
                            reason      = f'Source "{source_name}" in this citation has the usage of "{source_usage}", which is conflicting with other citations.',
                        )]



    return database, issues



################################################################################################################################



def log_issues(issues):
    for issue, ljust in zip(issues, ljusts((issue.file_path, issue.line_number) for issue in issues)):
        log('[WARNING] {0} : {1} | {2}'.format(*ljust, issue.reason), ansi = 'fg_yellow')



################################################################################################################################


@ui('Find citations and source declarations that refer to a specific source name.')
def find(
    specific_source_name : (str          , 'Source name to search for; otherwise, list everything.') = None,
    rename               : ((str, 'flag'), 'Change the source name of all occurrences.'            ) = None,
):

    database, issues = get_citations()



    # We list every citation.

    if specific_source_name is None:



        # Renaming citation sources can't be done without first specifying the original.

        if rename is not None:
            ui.help(subcommand_name = 'find')
            log()
            log(
                f'[ERROR] A source name must be provided in order to do a renaming; '
                f'see subcommand help above.',
                ansi = 'fg_red'
            )
            return 1







#        rows = []
#
#
#        for source_name, source_usage_citations in database.items():
#
#            match source_usage_citations:
#
#
#
#                # A source with a single definition and some citations that reference it.
#
#                case { 'definition': [definition], 'reference': references, **rest } if not rest:
#
#                    
#
#
#                case _:
#                    pass








#        rows = []
#
#        for source_name, (definitions, references) in database.items():
#
#            for reference_i, reference in enumerate(references):
#
#                row = {
#                    'file_path'   : reference.file_path,
#                    'line_number' : reference.line_number,
#                    'pg'          : f'pg {reference.fields['pg']}' if 'pg' in reference.fields else '',
#                    'listing'     : f'{reference.listing} {reference.fields[reference.listing]}' if reference.listing is not None else '',
#                }
#                definition_preview = ('', '', '')
#
#
#                match definitions:
#
#
#
#                    # These citations do not 
#
#                    case []:
#
#                        if reference.type is None:
#                            file_path   = '???'
#                            line_number = '???'
#                        else:
#                            file_path   = reference.file_path
#                            line_number = reference.line_number
#
#                        start = reference.source_name_columns[0] - reference.column
#                        end   = reference.source_name_columns[1] - reference.column
#
#                        definition_preview = (
#                            f' [{file_path}:{line_number}] {reference.text[:start]}',
#                            reference.text[start:end],
#                            reference.text[end:],
#                        )
#
#
#                    case [definition]:
#
#                        if reference_i == 0:
#
#                            start = definition.source_name_columns[0] - definition.column
#                            end   = definition.source_name_columns[1] - definition.column
#
#                            definition_preview = (
#                                f' [{definition.file_path}:{definition.line_number}] {definition.text[:start]}',
#                                definition.text[start:end],
#                                definition.text[end:],
#                            )
#
#
#
#                    case definitions:
#
#                        if reference_i == 0:
#
#                            definition_preview = (
#                                f' [???:???] {CITATION_TAG}/`',
#                                source_name,
#                                '`',
#                            )
#
#                rows += [(row, definition_preview)]
#
#
#        for ljust, definition_preview in zip(ljusts(row for row, definition_preview in rows), (definition_preview for row, definition_preview in rows)):
#            log('| {file_path} : {line_number} | {pg} | {listing} |'.format(**ljust), end = '')
#            log(definition_preview[0], end = '')
#            log(definition_preview[1], end = '', ansi = ('fg_magenta', 'bold', 'underline'))
#            log(definition_preview[2], end = '')
#            log()


        if issues:
            log()
            log_issues(issues)

    else:

        #
        # If we're renaming, do some basic checks.
        #

        if rename is not None:

            rename = rename.strip()

            if '`' in rename:
                log(f'[ERROR] The new source name "{rename}" cannot have a backtick "`".', ansi = 'fg_red')
                return 1

        if rename == '':
            log(f'[ERROR] The source cannot be renamed to an empty string.', ansi = 'fg_red')
            return 1

        if rename == specific_source_name:
            log(f'[WARNING] The new source name "{rename}" is the same as the old one; no renaming will be done.', ansi = 'fg_yellow')
            return 0

        #
        # Find all citations and source declaration instances that match the given name.
        #

        occurrences = collections.defaultdict(lambda: [])

        for source in ledger.sources.values():
            for src in source:
                if src.source_name == specific_source_name:
                    occurrences[src.file_path] += [types.SimpleNamespace(
                        line_number = src.line_number,
                        span     = src.source_name_span,
                        line     = src.line,
                    )]

        for citation in ledger.citations:
            if citation.source_name == specific_source_name:
                occurrences[citation.file_path] += [types.SimpleNamespace(
                    line_number = citation.line_number,
                    span     = citation.source_name_span,
                    line     = citation.line,
                )]

        occurrences = dict(occurrences)

        if not occurrences:
            did_you_mean(
                f'No citations or source declarations associated with "{specific_source_name}" was found.',
                specific_source_name,
                { *ledger.sources, *[citation.source_name for citation in ledger.citations] },
                ansi = 'fg_yellow',
            )
            return 0

        #
        # Show the findings.
        #

        rows = [
            (file_path, instance)
            for file_path, instances in occurrences.items()
            for instance in instances
        ]

        rows = zip(rows, ljusts((file_path, instance.line_number) for file_path, instance in rows))

        for (file_path, instance), columns in rows:
            log('| {0} : {1} | '.format(*columns), end = '')
            log(instance.line[                 : instance.span[0]].lstrip(), end = '')
            log(instance.line[instance.span[0] : instance.span[1]]         , end = '', ansi = ('fg_magenta', 'bold', 'underline'))
            log(instance.line[instance.span[1] :                 ].rstrip(), end = '')
            log()

        #
        # Rename the sources if requested.
        #

        if rename is not None:

            if ledger.issues:
                log()
                log_issues(ledger.issues)

            if (
                any(source_name          == rename for source_name in ledger.sources  ) or
                any(citation.source_name == rename for source_name in ledger.citations)
            ):
                if not ledger.issues:
                    log()
                log(f'[WARNING] The new source name "{rename}" is the name of an already existing source.', ansi = 'fg_yellow')

            log()
            log(f'[NOTE]', end = '', ansi = ('bg_green', 'fg_black'))
            log(f' Enter "yes" to replace the source names with "{rename}" (otherwise, abort): ', end ='')

            if input() != 'yes':
                log(f'[NOTE]', end = '', ansi = ('bg_green', 'fg_black'))
                log(f' Aborted the renaming.')
                return 1

            for file_path, instances in occurrences.items():

                file_lines = open(file_path).read().splitlines()

                # Iterate through the citations on the line backwards
                # so we can replace the source name properly.
                for instance in sorted(instances, key = lambda instance: (instance.line_number, -instance.span[0])):

                    file_lines[instance.line_number - 1] = (
                        file_lines[instance.line_number - 1][:instance.span[0]] +
                        rename +
                        file_lines[instance.line_number - 1][instance.span[1]:]
                    )

                file_path.write_text('\n'.join(file_lines) + '\n')

            ledger = get_citations()

            log(f'[NOTE]', end = '', ansi = ('bg_green', 'fg_black'))
            log(f' Renamed {len([instance for instances in occurrences.values() for instance in instances])} instances.')

        #
        # Report issues.
        #

        if ledger.issues:
            log()
            log_issues(ledger.issues)
