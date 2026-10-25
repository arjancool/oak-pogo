# ADR-0013: React-frontend

- Status: Accepted
- Date: 2026-10-23

## Context

OAK heeft een webinterface nodig. Er was nog geen frontendcode. De opdracht voor OAK 2.0 schrijft React met TypeScript voor.

## Besluit

De frontend gebruikt React, TypeScript (strict), Vite, Tailwind CSS, TanStack Query, TanStack Table, React Router en Zod. Componenten volgen de stijl van shadcn/ui maar worden in de repository zelf beheerd. Tests draaien met Vitest en Playwright. De gebouwde frontend wordt door de backend als statische bestanden geserveerd.

## Gevolgen

- Er is geen Node.js-runtime nodig in de productiecontainer.
- Grote identifiers (Pokémon-ID's, tag-ID's) zijn in de frontend altijd strings. Het Zod-schema dwingt dat af.

## Verworpen alternatieven

Vue 3 met Pinia is verworpen omdat de opdrachtgever expliciet React vraagt en er geen bestaande code was om te behouden.
