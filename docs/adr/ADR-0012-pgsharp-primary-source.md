# ADR-0012: PGSharp-export als primaire databron

- Status: Accepted
- Date: 2026-10-23
- Supersedes: ADR-0011
- Besluit: DEC-003

## Context

OAK v1 was ontworpen rond Calcy IV-CSV-exports. Die bevatten geen stabiele identiteit per Pokémon, waardoor een categorisch matchingalgoritme nodig was (ADR-0011). De PGSharp-functie *Export Account Data* levert per Pokémon het interne 64-bitsidentificatienummer uit de game. Een echte export (oktober 2026, 983 Pokémon) bevestigt dat dit veld uniek en stabiel aanwezig is.

## Besluit

- De identiteit van een Pokémon is `trainer_account_id + source_pokemon_id`.
- `source_pokemon_id` is het PGSharp-veld `id`, opgeslagen en verstuurd als decimale string.
- Webhook en handmatige upload gebruiken exact dezelfde verwerkingspijplijn.
- Fuzzy matching op soort, CP of IV wordt niet gebruikt. Twee Pokémon met dezelfde soort en CP zijn nooit automatisch hetzelfde exemplaar.
- Calcy IV-import valt buiten OAK 2.0. De oude parser staat in `archive/oak-v1/`.

## Gevolgen

- Evolutie, power-up en movewijziging behouden de identiteit van het exemplaar.
- Een export zonder `id` per Pokémon kan niet als volledige inventaris worden verwerkt.
- Een eventuele toekomstige bron zonder stabiele ID vereist een nieuwe ADR.

## Verworpen alternatieven

Matching op zichtbare eigenschappen is verworpen omdat PGSharp een betere, exacte identiteit levert.
