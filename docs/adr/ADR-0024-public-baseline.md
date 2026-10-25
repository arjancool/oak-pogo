# ADR-0024: Een openbare repository met alleen de huidige stand

- Status: Accepted
- Date: 2026-10-25
- Vervangt: ADR-0023

## Context

OAK staat in een openbare repository die met één commit begint. Daarvoor zijn de oude implementatie, losse projecten en vervangen ADR's verwijderd (ADR-0023). Daarna stonden er nog verwijzingen naar die verwijderde bestanden in de documentatie en in geaccepteerde ADR's. Ook was er een apart besluitenregister in `docs/DECISIONS.md`. Dat herhaalde wat in de ADR's staat en noemde de persoon die besliste met volledige naam.

## Besluit

- De repository bevat alleen wat OAK nu is. Oude versies worden niet in een map bewaard.
- Een ADR die door een nieuwe ADR wordt vervangen, gaat uit de repository. `docs/adr/README.md` noemt welke nummers daardoor ontbreken.
- Er is geen apart besluitenregister. Een ADR is het verslag van een besluit. De verwijzingen naar besluitnummers (`DEC-…`) vervallen.
- Bij de start van de openbare repository zijn de geaccepteerde ADR's eenmalig opgeschoond. Verwijzingen naar verwijderde ADR's, naar de oude implementatie en naar het besluitenregister zijn eruit gehaald. De besluiten zelf zijn niet veranderd. Daarna geldt weer dat een geaccepteerde ADR alleen verandert via een nieuwe ADR.
- Documentatie noemt geen persoonsgegevens van de eigenaar of van gebruikers.

## Gevolgen

- ADR-0023 is vervangen en staat niet meer in de repository.
- Wie wil weten waarom iets zo is, leest de ADR. Er is geen tweede bron die ermee in strijd kan raken.
