// jsdom reports an English browser. On a first visit OAK follows the browser language, and the
// unit tests expect the Dutch texts, so they run in a Dutch browser like the end-to-end tests.
Object.defineProperty(window.navigator, "languages", { value: ["nl-NL", "nl"], configurable: true });
Object.defineProperty(window.navigator, "language", { value: "nl-NL", configurable: true });
