# Regels voor AI-agents en automatisering

Deze regels gelden voor iedere AI-agent en iedere automatisering die in deze repository werkt.

## Volgorde van gezag

1. Veiligheids- en beveiligingsinvarianten hieronder.
2. Expliciete besluiten van de eigenaar, in de opdracht of in een ADR.
3. Geaccepteerde ADR's in `docs/adr/`.
4. De documentatie in `docs/`.
5. API-contracten (OpenAPI van de backend).
6. Acceptatiecriteria van een issue.
7. De bestaande implementatie.
8. Aannames van de agent.

Als twee bronnen elkaar tegenspreken, stop dan en meld het conflict.

## Veiligheidsinvarianten

- Verwijder of transfer nooit een Pokémon via automatisering.
- Overschrijf nooit een handmatige beslissing van de gebruiker tijdens een import.
- Markeer een Pokémon nooit als verdwenen op basis van een import waarvan de volledigheid niet vaststaat.
- Verzwak nooit de isolatie tussen gebruikers en traineraccounts.
- Log nooit secrets, webhook-tokens, sessietokens, wachtwoorden of ruwe exportinhoud.
- Bewaar geen locatiegegevens of interne spelersidentificaties uit PGSharp-exports.
- Stuur collectiegegevens nooit naar een externe AI-dienst zonder expliciete configuratie en toestemming.
- Iedere aanbeveling bevat redenen, herkomst en betrouwbaarheid.
- Zet een favoriet, een vintage Pokémon (2016–2019) of een Pokémon met onbekende vangstdatum nooit zonder bevestiging per Pokémon op een transferlijst (ADR-0019).

## Wijzigingsdiscipline

- Kleine, reviewbare pull requests.
- Geen speculatieve abstracties.
- Een ADR voor architectuurwijzigingen.
- Een migratie voor iedere wijziging van het databaseschema.
- Tests voor publieke API's.
- Deterministische domeinlogica.
- AI-uitvoer blijft buiten de deterministische beslislogica.
