# ADR-0023: Een openbare repository zonder oude versies

- Status: Accepted
- Date: 2026-10-25
- Besluit: DEC-008

## Context

De repository wordt openbaar. Hij bevatte nog veel dat niet bij OAK 2.0 hoort:

- de oude Calcy IV- en PostgreSQL-implementatie in `archive/oak-v1/`;
- het losse project Hermes-Oak in `hermes-oak/`;
- het bewijsmateriaal van een orchestratieronde in `evidence/`;
- de orchestratieregels in `docs/00-governance/` en het Engelstalige `GOVERNANCE.md` van de vorige versie;
- zeven ADR's die al vervangen waren: 0002, 0004, 0005, 0006, 0008, 0011 en 0018.

DEC-003 had besloten de oude implementatie in een map te bewaren in plaats van te verwijderen.

## Besluit

- Al die bestanden gaan uit de repository. Oude versies worden niet in een map bewaard.
- De openbare repository begint met één commit, zonder de eerdere geschiedenis. Die blijft alleen in de privérepository, zolang de eigenaar die bewaart.
- Het besluitenregister staat voortaan in `docs/DECISIONS.md`. De besluiten over de vorige orchestratie (DEC-001 en DEC-002) vervallen.
- Een geaccepteerde ADR verandert alleen via een nieuwe ADR. Daarom blijven de geaccepteerde ADR's ongewijzigd. Noemen ze een vervangen ADR of `archive/oak-v1/`, dan beschrijft dat hoe het besluit tot stand kwam. Die bestanden staan niet meer in de repository.
- ADR-0010 blijft gelden. OAK heeft geen koppeling met Hermes, ook nu Hermes-Oak niet meer in deze repository staat.

## Gevolgen

- Wie de oude implementatie of Calcy IV-import zoekt, vindt die niet in de openbare repository.
- `docs/adr/README.md` noemt welke ADR-nummers ontbreken en waarom.
- De Docker-build, de tests en de documentatie verwijzen niet meer naar de verwijderde mappen.
