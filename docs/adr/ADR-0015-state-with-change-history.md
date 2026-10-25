# ADR-0015: Actuele staat met onveranderlijke wijzigingshistorie

- Status: Accepted
- Date: 2026-10-23
- Supersedes: ADR-0005, ADR-0006
- Besluit: DEC-003

## Context

ADR-0005 en ADR-0006 schreven volledige event sourcing en CQRS voor. Een PGSharp-export is telkens een volledige momentopname van de inventaris. De vraag die de gebruiker stelt is vooral wat de huidige staat is en wat er tussen twee synchronisaties veranderde.

## Besluit

- Tabellen met de actuele staat (Pokémon, items, trainerstatistieken) zijn leidend.
- Iedere synchronisatie schrijft onveranderlijke wijzigingsgebeurtenissen per Pokémon (`APPEARED`, `CHANGED`, `DISAPPEARED`, `REAPPEARED`) met de gewijzigde velden. `APPEARED` bevat de volledige genormaliseerde staat, zodat de historie van ieder exemplaar reconstrueerbaar is.
- Een databasetrigger verbiedt het wijzigen van wijzigingsgebeurtenissen.
- Afgeleide gegevens (level, soortnaam, PvP-rangen, cleanup-adviezen) zijn projecties. Ze worden opnieuw berekend na een import, na een Game Data-wissel of op verzoek.
- Schrijfacties lopen via applicatieservices. Leesacties gebruiken aparte queryservices. Dat is een lichte scheiding, geen volledige CQRS met aparte opslag.

## Gevolgen

- Identieke synchronisaties leveren geen nieuwe gebeurtenissen op.
- Historie blijft compact, ook bij dagelijkse synchronisatie van duizenden Pokémon.

## Verworpen alternatieven

Volledige event sourcing is verworpen omdat de bron zelf al momentopnamen levert en replay van duizenden gebeurtenissen per sync geen toegevoegde waarde heeft.
