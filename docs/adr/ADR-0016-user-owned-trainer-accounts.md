# ADR-0016: Gebruikers en traineraccounts als isolatiegrens

- Status: Accepted
- Date: 2026-10-23

## Context

OAK kent gebruikers die meerdere Pokémon GO-traineraccounts beheren. Een model met tenants, lidmaatschappen en rollen is daarvoor zwaarder dan nodig.

## Besluit

- Iedere traineraccount hoort bij precies één gebruiker.
- Iedere query en opdracht op accountgebonden gegevens filtert verplicht op de traineraccount én de ingelogde gebruiker. Repositories accepteren geen accountgegevens zonder die scope.
- De rol `owner` beheert gebruikers en systeeminstellingen, maar krijgt geen toegang tot de Pokémon-gegevens van andere gebruikers.
- Een onbekend of andermans account-ID levert `404` op, niet `403`, zodat het bestaan van accounts niet uitlekt.

## Gevolgen

- Delen van een account tussen gebruikers is niet mogelijk. Dat vraagt later een nieuwe ADR.
- Tests controleren expliciet dat gebruiker A geen gegevens van gebruiker B ziet.
