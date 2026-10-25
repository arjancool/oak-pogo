# ADR-0012: PGSharp-export als primaire databron

- Status: Accepted
- Date: 2026-10-23

## Context

OAK moet iedere Pokémon over meerdere synchronisaties heen herkennen. Exports van scanapps zoals Calcy IV bevatten geen stabiele identiteit per Pokémon. Dan kun je exemplaren alleen koppelen op zichtbare eigenschappen, en dat gaat mis bij twee gelijke exemplaren. De PGSharp-functie *Export Account Data* levert per Pokémon het interne 64-bitsidentificatienummer uit de game. Een echte export (oktober 2026, 983 Pokémon) bevestigt dat dit veld uniek en stabiel aanwezig is.

## Besluit

- De identiteit van een Pokémon is `trainer_account_id + source_pokemon_id`.
- `source_pokemon_id` is het PGSharp-veld `id`, opgeslagen en verstuurd als decimale string.
- Webhook en handmatige upload gebruiken exact dezelfde verwerkingspijplijn.
- Fuzzy matching op soort, CP of IV wordt niet gebruikt. Twee Pokémon met dezelfde soort en CP zijn nooit automatisch hetzelfde exemplaar.
- Import uit Calcy IV valt buiten OAK.

## Gevolgen

- Evolutie, power-up en movewijziging behouden de identiteit van het exemplaar.
- Een export zonder `id` per Pokémon kan niet als volledige inventaris worden verwerkt.
- Een eventuele toekomstige bron zonder stabiele ID vereist een nieuwe ADR.

## Verworpen alternatieven

Matching op zichtbare eigenschappen is verworpen omdat PGSharp een betere, exacte identiteit levert.
