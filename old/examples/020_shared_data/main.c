#include <stdio.h>

extern int
main(void)
{
    #include "characters_enum.h"
    /* #meta
        Meta.enums('Character', 'u32', [character.name for character in CHARACTERS])
    */

    /* #meta CHARACTERS
        CHARACTERS = Table(
            ('name'        , 'level', 'vitality', 'attack', 'endurance', 'strength', 'dexterity', 'resistance', 'intelligence', 'faith', 'humanity'),
            ('Warrior'     , 4      , 11        , 8       , 12         , 13        , 13         , 11          , 9             , 9      , 0         ),
            ('Knight'      , 5      , 14        , 10      , 10         , 11        , 11         , 10          , 9             , 11     , 0         ),
            ('Wanderer'    , 3      , 10        , 11      , 10         , 10        , 14         , 12          , 11            , 8      , 0         ),
            ('Thief'       , 5      , 9         , 11      , 9          , 9         , 15         , 10          , 12            , 11     , 0         ),
            ('Bandit'      , 4      , 12        , 8       , 14         , 14        , 9          , 11          , 8             , 10     , 0         ),
            ('Hunter'      , 4      , 11        , 9       , 11         , 12        , 14         , 11          , 9             , 9      , 0         ),
            ('Sorcerer'    , 3      , 8         , 15      , 8          , 9         , 11         , 8           , 15            , 8      , 0         ),
            ('Pyromancer'  , 1      , 10        , 12      , 11         , 12        , 9          , 12          , 10            , 8      , 0         ),
            ('Cleric'      , 2      , 11        , 11      , 9          , 12        , 8          , 11          , 8             , 14     , 0         ),
            ('Deprived'    , 6      , 11        , 11      , 11         , 11        , 11         , 11          , 11            , 11     , 0         ),
        )
    */
}
