# Beveiligingsbeleid

## Een kwetsbaarheid melden

Meld een kwetsbaarheid niet in een openbaar issue. Gebruik op GitHub **Security → Report a vulnerability** als dat voor deze repository aanstaat, of neem rechtstreeks contact op met de beheerder van de repository.

Vermeld:

- Welke versie of commit je gebruikt.
- Hoe het probleem te reproduceren is.
- Wat een aanvaller ermee kan.

Stuur geen echte exports, webhook-URL's of wachtwoorden mee.

## Ondersteunde versies

Alleen de nieuwste versie op `main`, en de image `ghcr.io/arjancool/oak-pogo:latest`, krijgt beveiligingsupdates.

## Uitgangspunten

- OAK vraagt nooit om Pokémon GO-inloggegevens en voert nooit gameplay-acties uit.
- Gebruikers zien alleen hun eigen traineraccounts.
- Wachtwoorden, sessietokens en webhook-tokens staan alleen als hash in de database en komen nooit in het logboek.
- Geen standaardwachtwoorden en geen geheimen in de repository.

Hoe dat technisch is ingericht, staat in `docs/SECURITY.md`.
