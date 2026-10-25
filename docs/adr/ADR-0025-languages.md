# ADR-0025: Meertaligheid

- Status: Accepted
- Date: 2026-10-25

## Context

OAK staat in een openbare repository en is alleen in het Nederlands te gebruiken. De eigenaar wil OAK in meer talen aanbieden. De meeste teksten staan nu direct in de React-componenten. De backend levert daarnaast Nederlandse zinnen: redenen in het cleanupadvies, foutmeldingen en eventredenen. De redenen hebben al een code en gegevens naast de tekst, en iedere foutmelding heeft een code.

## Besluit

- De frontend vertaalt met i18next en react-i18next. Iedere taal heeft één bestand in `frontend/src/i18n/`. Nederlands is de brontaal: een nieuwe tekst komt eerst in `nl.json`.
- Een test faalt als een taal een sleutel mist of een sleutel heeft die het Nederlands niet kent, of als een tekst leeg is. TypeScript controleert dat iedere gebruikte sleutel in `nl.json` bestaat.
- De eerste extra taal is Engels. Een taal toevoegen is een bestand toevoegen en het in de lijst van talen zetten.
- Iedere gebruiker kiest een taal. De keuze staat bij de gebruiker (`preferences.language`) en op het apparaat. De backend controleert alleen dat het een code van twee letters is. Welke talen er zijn, bepaalt de frontend.
- Zolang niet alles vertaald is, blijft Nederlands de standaard en heet Engels in de keuzelijst *English (beta)*. Daarna volgt OAK zonder keuze de taal van de browser.
- Getallen en datums volgen de gekozen taal. Een browserinstelling in dezelfde taal gaat voor, zodat bijvoorbeeld iemand in de Verenigde Staten de eigen datumvolgorde houdt.
- De backend stuurt voor teksten die vertaald moeten worden een code met gegevens. De frontend maakt daar de zin van. De Nederlandse tekst blijft als terugval tot alles is omgezet.
- Vaste termen uit `CLAUDE.md` krijgen per taal één vaste vertaling. *Niet meer in inventaris* wordt in het Engels *No longer in inventory*, *onbekend* wordt *unknown*.
- Zoekteksten voor in het spel volgen de taal van Pokémon GO, niet die van OAK. Dat wordt een eigen instelling.
- Namen van Pokémon en aanvallen blijven zoals ze in de Game Data staan. Vertaalde namen vragen een nieuwe databron en een eigen ADR.

## Gevolgen

- De omzetting gaat per pagina, in kleine stappen. Tot die klaar is, kan een Engelstalige gebruiker nog Nederlandse teksten zien.
- Nieuwe teksten in de frontend horen in de vertaalbestanden, niet in de componenten.
- De documentatie blijft Nederlands. Een Engelse README is een aparte stap.
