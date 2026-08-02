export function evaluatePolicy(document) {
  return document.rules.map(rule => rule.evaluate(document));
}
